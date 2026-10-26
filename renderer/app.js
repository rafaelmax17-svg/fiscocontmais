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
  const navBtn = document.querySelector(`.nav .nav-item[data-view="${name}"]`);
  if (navBtn && navBtn.classList.contains('role-hidden')) return;      // módulo não liberado para este usuário
  if (name !== 'manual-fiscal' && window._manualSair) window._manualSair();
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  const hasData = !!DATA;
  const contabil = ['overview', 'dre', 'balancete', 'invertidas', 'indicadores'];
  $('#empty').hidden = !(contabil.includes(name) && !hasData);
  document.body.dataset.areaContabil = contabil.includes(name) ? '1' : '';
  _atualizaTopo();
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
  if (name === 'fiscal-pgdas') { $('#view-fiscal-pgdas').hidden = false; $('#empty').hidden = true; if (window.fechEntrar) window.fechEntrar(); return; }
  const stg = document.querySelector('.stage'); if (stg) stg.classList.toggle('stage-cheia', name === 'manual-fiscal');
  if (name === 'fiscal-manifestacao') { $('#view-fiscal-manifestacao').hidden = false; $('#empty').hidden = true; if (window._manifEntrar) window._manifEntrar(); return; }
  if (name === 'manual-fiscal') { $('#view-manual-fiscal').hidden = false; $('#empty').hidden = true; if (window._manualEntrar) window._manualEntrar(); return; }
  if (name === 'fiscal-downloads') { $('#view-fiscal-downloads').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'fiscal-efd-contrib') {
    $('#view-fiscal-efd-contrib').hidden = false; $('#empty').hidden = true;
    const fr = $('#efdFrame'); if (fr && fr.srcdoc) fr.srcdoc = fr.srcdoc;   // recarrega: a animação do painel toca de novo
    return;
  }
  if (name === 'admin-lic') { $('#view-admin-lic').hidden = false; $('#empty').hidden = true; loadLicensePanel(); return; }
  if (name === 'admin-usuarios') { $('#view-admin-usuarios').hidden = false; $('#empty').hidden = true; loadUsuarios(); return; }
  if (name === 'admin-corrigir-sped') { $('#view-admin-corrigir-sped').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'admin-corrigir-efd') { $('#view-admin-corrigir-efd').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'admin-lmc') { $('#view-admin-lmc').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'admin-audam') { $('#view-admin-audam').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'admin-evo') { $('#view-admin-evo').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'admin-radar') { $('#view-admin-radar').hidden = false; $('#empty').hidden = true; return; }
  if (name === 'admin-legal') { $('#view-admin-legal').hidden = false; $('#empty').hidden = true; return; }
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
      overlay(true, 'Cruzando XMLs de saída com o SPED… (com dezenas de milhares de notas leva alguns segundos)');
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
    const btnLote = $('#btnNflBaixar');
    if (btnLote) btnLote.disabled = !(temEmpresa && temPasta);
    dlAtualizarBotaoPainel();
  }

  // window.prompt não existe no Electron — mini-modal próprio para o CNPJ da filial
  function dlPedirCnpjFilial(emp) {
    return new Promise((resolve) => {
      const fundo = document.createElement('div');
      fundo.style.cssText = 'position:fixed;inset:0;background:rgba(20,23,51,.45);display:flex;align-items:center;justify-content:center;z-index:600';
      fundo.innerHTML = `<div style="background:var(--panel);border-radius:12px;padding:22px 24px;width:400px;max-width:90vw">
        <div style="font-size:15px;font-weight:600;margin-bottom:4px">Cadastrar filial</div>
        <div style="font-size:12px;color:var(--ink2);margin-bottom:14px">Usa o certificado de <b>${_esc(emp.razaoSocial || '')}</b> (${_esc(_fmtCnpjJs(emp.cnpj || ''))}). A filial precisa ter a mesma raiz: <b>${_esc(String(emp.cnpj || '').slice(0, 8))}</b>…</div>
        <label style="font-size:11px;color:var(--ink2);display:block;margin-bottom:5px">CNPJ da filial</label>
        <input type="text" maxlength="18" placeholder="00.000.000/0002-00" style="width:100%;margin-bottom:16px">
        <div style="display:flex;justify-content:flex-end;gap:10px">
          <button class="act inv-export" data-a="nao">Cancelar</button>
          <button class="act inv-export" data-a="sim" style="background:#1f2a5a;color:#fff;border-color:transparent">Salvar filial</button>
        </div></div>`;
      document.body.appendChild(fundo);
      const inp = fundo.querySelector('input');
      inp.value = String(emp.cnpj || '').slice(0, 8);
      inp.focus();
      inp.addEventListener('input', () => {
        const d = inp.value.replace(/\D/g, '').slice(0, 14);
        inp.value = d.length === 14 ? _fmtCnpjJs(d) : d;
      });
      const fim = (v) => { fundo.remove(); resolve(v); };
      fundo.querySelector('[data-a="nao"]').onclick = () => fim(null);
      fundo.querySelector('[data-a="sim"]').onclick = () => {
        const d = inp.value.replace(/\D/g, '');
        if (d.length !== 14) { toast('Digite os 14 dígitos do CNPJ da filial.', true); return; }
        fim(d);
      };
      inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') fundo.querySelector('[data-a="sim"]').click(); if (ev.key === 'Escape') fim(null); });
    });
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
        <td style="padding:9px 8px">${_esc(e.razaoSocial)} <span class="dl-badge ${e.tipo === 'filial' ? 'fil' : 'mat'}">${e.tipo === 'filial' ? 'Filial' : 'Matriz'}</span>${e.tipo === 'filial' ? `<div style="font-size:10.5px;color:var(--ink2)">certificado da matriz ${_esc(_fmtCnpjJs(e.cnpjCert))}</div>` : ''}</td>
        <td style="padding:9px 8px;color:var(--ink2)">${_esc(_fmtCnpjJs(e.cnpj))}</td>
        <td style="padding:9px 8px"><span style="${corBadge};font-size:11px;padding:2px 9px;border-radius:6px">${_esc(validadeTexto)}</span></td>
        <td style="padding:9px 8px;color:var(--ink2)">${_esc(ultimoTexto)}</td>
        <td style="padding:9px 8px;text-align:right;white-space:nowrap">${e.tipo !== 'filial' ? `<button class="act inv-export" data-filial="${_esc(e.id)}" style="padding:3px 10px;font-size:11px" title="Cadastrar uma filial usando este mesmo certificado">+ Filial</button> ` : ''}<button class="act inv-export" data-remover="${_esc(e.id)}" style="padding:3px 10px;font-size:11px">Remover</button></td>
      </tr>`;
    }).join('');
    corpo.querySelectorAll('button[data-filial]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const emp = DL_EMPRESAS.find((x) => x.id === btn.dataset.filial) || {};
        const cnpj = await dlPedirCnpjFilial(emp);
        if (!cnpj) return;
        const res = await window.fiscocont.fiscal.certAddFilial(btn.dataset.filial, cnpj);
        if (res.error) { toast(res.error, true); return; }
        toast(`Filial cadastrada: ${res.razaoSocial}`);
        dlCarregarEmpresas();
      });
    });
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
      $('#dlCertTipoBox').hidden = true;
      $('#dlCertFilialBox').hidden = true;
      $('#dlCertCnpjFilial').value = '';
      document.querySelector('input[name="dlCertTipo"][value="matriz"]').checked = true;
      $('#btnDlCertSalvar').hidden = true;
      $('#dlModalCert').hidden = false;
    });
    document.querySelectorAll('input[name="dlCertTipo"]').forEach((r) => r.addEventListener('change', () => {
      $('#dlCertFilialBox').hidden = r.value !== 'filial' || !r.checked;
      if (r.value === 'filial' && r.checked) $('#dlCertCnpjFilial').focus();
    }));
    $('#dlCertCnpjFilial').addEventListener('input', (ev) => {
      const d = ev.target.value.replace(/\D/g, '').slice(0, 14);
      ev.target.value = d.length === 14 ? _fmtCnpjJs(d) : d;
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
      $('#dlCertTipoBox').hidden = false;
      $('#btnDlCertSalvar').hidden = false;
    });

    $('#btnDlCertSalvar').addEventListener('click', async () => {
      if (!dlCertInfo || !dlCertPfxPath) return;
      const senha = $('#dlCertSenha').value;
      overlay(true, 'Salvando…');
      const tipo = (document.querySelector('input[name="dlCertTipo"]:checked') || {}).value || 'matriz';
      const cnpjFilial = $('#dlCertCnpjFilial').value.replace(/\D/g, '');
      if (tipo === 'filial' && cnpjFilial.length !== 14) { overlay(false); toast('Digite o CNPJ completo da filial.', true); return; }
      const res = await window.fiscocont.fiscal.certSalvar(dlCertPfxPath, senha, dlCertInfo, tipo, cnpjFilial);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      toast(tipo === 'filial' ? 'Filial cadastrada — as notas vão para a pasta própria da filial.' : 'Empresa cadastrada.');
      $('#dlModalCert').hidden = true;
      dlCarregarEmpresas();
      if (window._manifPendente) window._manifPendente();     // veio da Consulta Manifestação: volta para ela
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
        ${gerarPdf ? `<div style="margin-top:10px;font-size:12px;color:var(--ink2)">PDFs (DANFSe) gerados: <b>${r.pdfs_gerados || 0}</b>${r.pdfs_erro ? ` · <span style="color:#c92a2a">${r.pdfs_erro} com erro ao gerar</span>` : ''}</div>
          ${r.outros_cnpj ? `<div style="margin-top:6px;font-size:12px;background:#f3f4fb;border-radius:8px;padding:8px 10px;color:#3a4270"><b>${r.outros_cnpj} nota(s) de outro CNPJ</b> (ex.: da matriz ou de outra filial) vieram na consulta e foram separadas na pasta <b>NFS-e\\Outros CNPJ</b> — não entram em Prestados/Tomados nem nos totais desta empresa.</div>` : ''}
          ${(r.pdfs_erros || []).length ? `<div style="margin-top:6px;font-size:12px;background:#fdf0f0;border-radius:8px;padding:8px 10px;color:#791f1f">${r.pdfs_erros.map((x) => `<div><b>NFS-e ${_esc(x.nnfse || '')}</b> <span style="color:#a05050;font-family:monospace;font-size:10.5px">…${_esc((x.chave || '').slice(-12))}</span> — ${_esc(x.motivo || '')}</div>`).join('')}<div style="margin-top:4px;color:#8a5a5a">O XML foi salvo normalmente. O botão <b>PDF</b> da nota, no painel, gera o PDF de novo.</div></div>` : ''}` : ''}
        <div style="margin-top:6px;font-size:12px;color:var(--ink2)">Salvo em: ${_esc(r.pasta)}</div>
        <button class="act inv-export" id="btnDlAbrirPasta" style="margin-top:10px">Abrir pasta</button>`;
      $('#btnDlAbrirPasta').addEventListener('click', () => window.fiscocont.openPath(r.pasta));
      toast(`${r.salvos} nota(s) baixada(s).`);
      dlCarregarEmpresas();
      dlAnalisar(); // mostra o painel sozinho assim que termina de baixar
    });
    dlCarregarEmpresas();
    dlCarregarPasta();
    document.addEventListener('fiscocont:dl-recarregar', () => dlCarregarEmpresas());   // a baixa em lote atualiza a lista (último download)

    // botão "PDF" de cada nota, clicado dentro do iframe do painel — o
    // próprio iframe manda um postMessage (não dá pra addEventListener
    // direto num elemento de dentro de um srcdoc de outra origem)
    window.addEventListener('message', async (ev) => {
      if (!ev.data || ev.data.tipo !== 'fiscocont-nfse-pdf') return;
      // achado real (Rafael, 14/10): usava a empresa selecionada AGORA na lista — se ela foi trocada
      // depois de montar o painel, procurava o XML na pasta da empresa errada. Vale a do painel.
      const empresaId = (DL_PAINEL_PERIODO && DL_PAINEL_PERIODO.empresaId) || $('#dlSelectEmpresa').value;
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
    const XMLS = { path: null };   // XMLs de entrada (.zip) do Corretor: usados no DIFAL e no crédito do Simples
    let corrFeito = false;   // true depois de "Corrigir SPED" ou de aplicar o DIFAL neste arquivo
    // ⚡ Automatizar correção → "Abrir no modo manual" de um cliente: escolhe o SPED (e a pasta de XMLs) como se fosse à mão
    window.__corrAbrirManual = (sped, xmls) => {
      corrSpedPath = sped; FISCAL.corrSpedPath = sped;
      ['#btnCorrSpedVerOriginal', '#btnCorrSpedRodar', '#btnCorrDifal', '#btnCorrSimples'].forEach((id) => { $(id).disabled = false; });
      corrFeito = false;
      SN.an = null; XMLS.path = xmls || null;
      $('#corrSimples').hidden = true; $('#corrSimples').innerHTML = '';
      $('#corrSpedResumo').hidden = true;
      $('#corrDifal').hidden = true; $('#corrDifal').innerHTML = '';
      $('#corrLote').hidden = true; $('#corrIcmsXml').hidden = true; $('#corrValXml').hidden = true; $('#corrEstST').hidden = true; $('#btnCorrIcmsXml').disabled = false; $('#btnCorrValXml').disabled = false; $('#btnCorrEstST').disabled = false;
      $('#corrSpedFrame').hidden = true; $('#corrSpedEmpty').hidden = false;
      toast('Modo manual: ' + sped.split(/[\\/]/).pop() + (xmls ? ' (XMLs de entrada já anexados)' : ''));
    };
    bCorrPick.addEventListener('click', async () => {
      const pick = await window.fiscocont.fiscal.pickSped();
      if (pick.canceled || !pick.path) return;
      $('#corrLote').hidden = true;
      corrSpedPath = pick.path;
      FISCAL.corrSpedPath = pick.path;
      $('#btnCorrSpedVerOriginal').disabled = false;
      $('#btnCorrSpedRodar').disabled = false;
      $('#btnCorrDifal').disabled = false;
      $('#btnCorrSimples').disabled = false;
      corrFeito = false;
      SN.an = null; XMLS.path = null;
      $('#corrSimples').hidden = true; $('#corrSimples').innerHTML = '';
      $('#corrSpedResumo').hidden = true;
      $('#corrDifal').hidden = true; $('#corrDifal').innerHTML = '';
      $('#corrIcmsXml').hidden = true; $('#corrValXml').hidden = true; $('#corrEstST').hidden = true; $('#corrIcmsXml').innerHTML = ''; IX.an = null;
      $('#btnCorrIcmsXml').disabled = false; $('#btnCorrValXml').disabled = false; $('#btnCorrEstST').disabled = false;
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
      const res = await window.fiscocont.fiscal.corrigirSped(corrSpedPath, [], corrFeito);
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      corrFeito = true;
      $('#corrDifal').hidden = true;
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
            ${r.c197_campos_ajustados ? `<div><b style="font-size:20px;color:#1f2a5a">${r.c197_campos_ajustados}</b><br>C197/D197 com campo a mais corrigidos</div>` : ''}
            ${r.c100_totais_corrigidos ? `<div><b style="font-size:20px;color:#1f2a5a">${r.c100_totais_corrigidos}</b><br>C100 com total diferente do C190 corrigidos</div>` : ''}
            ${r.vl_merc_corrigidos ? `<div><b style="font-size:20px;color:#1f2a5a">${r.vl_merc_corrigidos}</b><br>Valor das mercadorias menor que a soma dos itens</div>` : ''}
            ${r.cod_sit_08 ? `<div><b style="font-size:20px;color:#1f2a5a">${r.cod_sit_08}</b><br>Notas com CNPJ da chave ≠ participante → situação 08</div>` : ''}
          </div>
          ${[...(r.vl_merc_detalhe || []), ...(r.cod_sit_08_detalhe || [])].length ? `<details style="margin-top:10px;font-size:12.5px"><summary style="cursor:pointer;color:#2f4090;font-weight:600">ver as notas (valor das mercadorias e situação 08)</summary><ul style="margin:6px 0 0 18px">${[...(r.vl_merc_detalhe || []), ...(r.cod_sit_08_detalhe || [])].map((x) => `<li>${String(x).replace(/[&<>]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]))}</li>`).join('')}</ul></details>` : ''}
          ${(r.c100_totais_detalhe || []).length ? `<details style="margin-top:10px;font-size:12.5px"><summary style="cursor:pointer;color:#2f4090;font-weight:600">ver as notas (C100 = soma do C190)</summary><ul style="margin:6px 0 0 18px">${r.c100_totais_detalhe.map((x) => `<li>${String(x).replace(/[&<>]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]))}</li>`).join('')}</ul></details>` : ''}
          ${r.e110_creditos ? `<div class="dif-av" style="margin-top:12px"><b>E110, campo 06 (créditos) recalculado pela soma das notas:</b> R$ ${(r.e110_creditos.antes).toLocaleString('pt-BR', { minimumFractionDigits: 2 })} → R$ ${(r.e110_creditos.depois).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
            · ICMS a recolher R$ ${(r.e110_creditos.recolher_antes).toLocaleString('pt-BR', { minimumFractionDigits: 2 })} → <b>R$ ${(r.e110_creditos.recolher_depois).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</b>${r.e110_creditos.e116 ? ' · ' + r.e110_creditos.e116 : ''}</div>` : ''}
          ${(r.avisos_c100_e110 || []).length ? `<div class="dif-av err" style="margin-top:12px"><ul>${r.avisos_c100_e110.map((x) => `<li>${String(x).replace(/[&<>]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]))}</li>`).join('')}</ul></div>` : ''}
          ${(r.avisos || []).length ? `<div class="dif-av" style="margin-top:14px"><b>Atenção antes de transmitir</b><ul>${r.avisos.map((x) => `<li>${String(x).replace(/[&<>]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]))}</li>`).join('')}</ul></div>` : ''}
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
      // o dashboard animado já vem junto com a correção e abre sozinho
      if (res.html) {
        const fr = $('#corrSpedFrame');
        fr.srcdoc = res.html;
        fr.hidden = false; $('#corrSpedEmpty').hidden = true;
        $('#corrDifal').hidden = true; $('#corrSimples').hidden = true;
      }
      toast('Correção concluída — confira o dashboard.');
    });

    // ---- Uso e consumo / ativo: CFOP 1.xxx x 2.xxx e DIFAL de RO (conferência + confirmação) ----
    $('#btnCorrDifal').addEventListener('click', () => difalAbrir());
    $('#btnCorrSimples').addEventListener('click', () => snAbrir());

    const DIF = { an: null, origem: null };
    const fm = (v) => (Number(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const fa = (v) => (Number(v) || 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + '%';
    const dt = (d) => d && d.length === 8 ? `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}` : (d || '');
    const r2 = (x) => Math.round((x + Number.EPSILON) * 100) / 100;
    const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    // espelho de difal_ro.calcular_difal (Lei 688/96, art. 18, IX, §§ 1º e 7º)
    function difCalc(valor, inter, interna, dupla) {
      const v = Number(valor) || 0, ai = (Number(inter) || 0) / 100, an = (Number(interna) || 0) / 100;
      if (an <= ai || v <= 0 || an >= 1) return { base: r2(v), difal: 0 };
      if (dupla) { const io = v * ai, base = (v - io) / (1 - an); return { base: r2(base), difal: r2(base * an - io) }; }
      return { base: r2(v), difal: r2(v * (an - ai)) };
    }
    const STATUS = {
      faltando: ['Falta DIFAL', 'b-err'], balcao: ['Balcão · sem DIFAL', 'b-info'], nf_fora: ['NF-e fora do SPED', 'b-warn'], divergente: ['DIFAL divergente', 'b-warn'], ok: ['DIFAL ok', 'b-ok'],
      pago_fora: ['Pago fora da apuração', 'b-info'], interna: ['Operação interna', 'b-mute'],
      cancelada: ['Cancelada', 'b-mute'], sem_uf: ['UF não identificada', 'b-warn'], st_nota: ['ICMS-ST retido na nota', 'b-info'],
    };
    // compra de balcão: a classificação (consumo × ativo) pode ser trocada na tela e muda o que é sugerido
    function efe(d) {
      const cl = d.balcao && DIF.classe && DIF.classe[d.id];
      if (cl && cl !== d.balcao.classe) {
        if (cl === 'ativo') {
          const st = d.difal_lancado > 0 ? (Math.abs(d.difal_lancado - d.difal_calculado) <= 0.05 ? 'ok' : 'divergente') : 'faltando';
          return { status: st, sugDifal: st !== 'ok', sugRem: false, classe: cl };
        }
        return { status: 'balcao', sugDifal: false, sugRem: d.difal_lancado > 0, classe: cl };
      }
      return { status: d.status, sugDifal: d.sugerido_difal, sugRem: d.sugerido_remover, classe: d.balcao ? d.balcao.classe : null };
    }
    const podeDifal = (d) => d.interestadual && (efe(d).status === 'faltando' || efe(d).status === 'divergente');

    async function difalAbrir() {
      if (!corrSpedPath) return;
      $('#corrIcmsXml').hidden = true; $('#corrValXml').hidden = true; $('#corrEstST').hidden = true;
      overlay(true, 'Conferindo notas de uso e consumo / ativo e o DIFAL de RO…');
      const res = await window.fiscocont.admin.difalAnalisar({ spedPath: corrSpedPath, usarCorrigido: corrFeito, xmls: XMLS.path });
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      DIF.an = res.res; DIF.origem = res.origem; DIF.classe = {};
      $('#corrSpedEmpty').hidden = true; $('#corrSpedFrame').hidden = true; $('#corrSpedResumo').hidden = true;
      $('#corrSimples').hidden = true;
      difalRender();
      animaNumeros($('#corrDifal'));
    }

    function difalRender() {
      const an = DIF.an, emp = an.empresa || {}, rs = an.resumo || {}, box = $('#corrDifal');
      const docs = an.docs || [];
      box.hidden = false;
      const naoRO = emp.uf && emp.uf !== 'RO';
      const linhas = docs.map((d) => {
        const ef = efe(d);
        const st = STATUS[ef.status] || [ef.status, 'b-mute'];
        const cfop = d.correcoes_cfop.length
          ? `<label class="dif-ck"><input type="checkbox" data-cfop="${d.id}" ${d.sugerido_cfop ? 'checked' : ''}> ${d.correcoes_cfop.map((c) => `${c.de} → <b>${c.para}</b>`).join('<br>')}</label>`
          : `<span class="dif-mute">${[...new Set(d.grupos.flatMap((g) => g.cfops))].join(', ')}</span>`;
        const ok = podeDifal(d) && !naoRO;
        const grupos = d.grupos.map((g, gi) => `
          <div class="dif-g" data-doc="${d.id}" data-g="${gi}">
            <span class="dif-tipo">${g.tipo === 'ativo' ? 'Ativo' : 'Uso/consumo'}</span>
            <span>R$ ${fm(g.valor)}</span>
            <select data-inter ${ok ? '' : 'disabled'} title="Alíquota interestadual (${esc(g.fonte_aliq)})">
              ${[4, 7, 12].map((x) => `<option value="${x}" ${Number(g.aliq_inter) === x ? 'selected' : ''}>${x}%</option>`).join('')}
            </select>
            <input data-interna type="number" step="0.01" min="0" max="99" value="${g.aliq_interna}" ${ok ? '' : 'disabled'} title="Alíquota interna de RO">
            <b class="dif-val" data-val>${d.interestadual ? 'R$ ' + fm(g.difal) : '—'}</b>
            ${d.interestadual && d.base_dupla === false ? '<span class="dif-b b-warn" title="Empresa do Simples Nacional: base única (Lei 688/96, art. 18, § 9º)">base única</span>' : ''}
            ${d.interestadual ? `<small class="dif-gsrc ${d.fonte === 'xml' ? 'xml' : ''}">${d.fonte === 'xml' ? `XML · ${g.itens || 0} item(ns) · origem ${esc((g.origens || []).join(', '))}` : 'alíquota deduzida pelo SPED'}</small>` : ''}
          </div>`).join('');
        return `
          <tr data-id="${d.id}" class="${ok ? '' : 'dif-off'}">
            <td>${ok ? `<input type="checkbox" data-difal="${d.id}" ${ef.sugDifal ? 'checked' : ''} title="Lançar DIFAL (C195/C197)">`
              : (ef.status === 'balcao' && d.difal_lancado > 0 ? `<input type="checkbox" data-rem="${d.id}" ${ef.sugRem ? 'checked' : ''} title="Retirar o DIFAL lançado (compra de balcão)">` : '')}</td>
            <td><b>${esc(d.num)}</b><small>${dt(d.data)}${d.serie ? ' · série ' + esc(d.serie) : ''}</small></td>
            <td>${esc(d.fornecedor)}${d.fornecedor_simples ? ` <span class="dif-b b-warn" title="Fornecedor do Simples Nacional (CRT ${esc(d.fornecedor_crt || '1')}): DIFAL com a alíquota interestadual cheia (LC 123/2006, art. 13, § 5º)">Simples</span>` : ''}<small>${esc(d.cnpj)}</small></td>
            <td><b>${esc(d.uf_origem || '?')}</b><small>${esc(d.fonte_uf || '')}</small></td>
            <td>${cfop}</td>
            <td>${grupos}</td>
            <td class="n">${d.difal_lancado ? 'R$ ' + fm(d.difal_lancado) : '—'}${d.difal_pago_fora ? `<small>pago fora: R$ ${fm(d.difal_pago_fora)}</small>` : ''}</td>
            <td><span class="dif-b ${st[1]}">${st[0]}</span>${(d.obs || []).map((o) => `<small class="dif-obs">${esc(o)}</small>`).join('')}</td>
          </tr>`;
      }).join('');
      const e116 = (an.e116 || []).find((x) => x.cod === '000');
      const e116Qq = (an.e116 || [])[0] || {};
      box.innerHTML = `
        <div class="dif-head">
          <div>
            <div class="dif-k">Uso e consumo / ativo · DIFAL de Rondônia e crédito de ICMS</div>
            <h3>${esc(emp.nome || '')}</h3>
            <div class="dif-sub">CNPJ ${esc(emp.cnpj || '')} · período ${dt(emp.dt_ini)} a ${dt(emp.dt_fin)} ·
              arquivo <b>${DIF.origem === 'corrigido' ? 'já corrigido nesta sessão' : 'original'}</b> ·
              ${(an.regime_empresa || {}).regime === 'simples' ? '<b>empresa do Simples Nacional</b> · base única (desde 11/06/2025)'
                : an.base_dupla ? 'base dupla (desde 01/04/2022)' : 'base única'} · alíquota interna ${fa(an.aliq_interna_padrao)}</div>
          </div>
          <div class="sn-hbtn"><button class="act inv-export" id="btnDifXmls">${XMLS.path ? 'Trocar XMLs' : 'Anexar XMLs de entrada'}</button><button class="act inv-export" id="btnDifFechar">Fechar</button></div>
        </div>
        ${XMLS.path ? `<div class="dif-av ok dif-xmlbar"><b>XMLs de entrada anexados:</b> ${rs.xml_lidos ?? 0} lido(s) · ${rs.xml_usados ?? 0} nota(s) conferida(s) item a item pelo XML (origem, alíquota destacada, IPI, frete e ICMS-ST)${rs.sem_xml ? ` · <b>${rs.sem_xml}</b> nota(s) interestadual(is) sem XML, pela regra do SPED` : ''}.</div>`
          : `<div class="dif-av dif-xmlbar"><b>Sem XMLs:</b> a alíquota interestadual está sendo deduzida pelo SPED (alíquota do C190 ou CST e UF). Anexe os XMLs de entrada para conferir item a item: produto importado a 4%, origem, IPI e ICMS-ST retido.
            <button class="act inv-export" id="btnDifXmls2">Anexar XMLs (.zip)</button></div>`}
        ${naoRO ? `<div class="dif-av err">Este SPED é de empresa de <b>${esc(emp.uf)}</b>. O lançamento automático do DIFAL só é feito para RO; a correção de CFOP continua disponível.</div>` : ''}
        ${(an.avisos || []).length ? `<div class="dif-av"><b>Atenção</b><ul>${an.avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
        <div class="dif-kpis">
          <div><span>Notas analisadas</span><b data-n="${rs.notas || 0}">0</b></div>
          <div class="k-err"><span>CFOP a corrigir</span><b data-n="${rs.cfop_errado || 0}">0</b><small>1.xxx com fornecedor de fora</small></div>
          <div class="k-err"><span>Sem DIFAL</span><b data-n="${rs.faltando || 0}">0</b><small>R$ ${fm(rs.difal_faltando)}</small></div>
          <div class="k-warn"><span>DIFAL divergente</span><b data-n="${rs.divergente || 0}">0</b></div>
          <div class="k-ok"><span>DIFAL correto</span><b data-n="${rs.ok || 0}">0</b></div>
          <div><span>Pago fora (RO90000002)</span><b data-n="${rs.pago_fora || 0}">0</b></div>
          ${rs.balcao ? `<div class="k-err"><span>Compras de balcão</span><b data-n="${rs.balcao}">0</b><small>DIFAL a retirar: R$ ${fm(rs.balcao_difal_indevido)}</small></div>` : ''}
          ${rs.fretes ? `<div class="k-err"><span>DIFAL do frete (CT-e)</span><b data-n="${rs.fretes_difal_faltando || 0}" data-fmt="brl">R$ 0,00</b><small>${rs.fretes_faltando || 0} de ${rs.fretes} CT-e sem DIFAL</small></div>` : ''}
          ${XMLS.path ? `<div class="k-warn"><span>Alíquota XML × SPED</span><b data-n="${rs.aliq_xml_diverge || 0}">0</b><small>DIFAL ${rs.dif_xml_sped >= 0 ? 'a mais' : 'a menos'} pelo XML: R$ ${fm(Math.abs(rs.dif_xml_sped || 0))}</small></div>
          <div><span>ICMS-ST retido na nota</span><b data-n="${rs.st_nota || 0}">0</b><small>sem DIFAL a lançar</small></div>` : ''}
        </div>
        ${difCompHtml(docs)}
        ${difBalcaoHtml(an)}
        ${difFreteHtml(an)}
        ${docs.length ? `
        <div class="dif-tw"><table class="dif-tab">
          <thead><tr><th><input type="checkbox" id="difTodos" title="Marcar/desmarcar o DIFAL de todas"></th><th>Nota</th><th>Fornecedor</th><th>UF</th><th>CFOP</th>
            <th>Itens · alíq. interestadual · interna · DIFAL</th><th class="n">Lançado</th><th>Situação</th></tr></thead>
          <tbody>${linhas}</tbody>
        </table></div>` : '<div class="dif-av">Nenhuma nota de uso e consumo (CFOP x.556/x.407) ou ativo (x.551/x.406) de outro estado ou com CFOP a corrigir neste SPED.</div>'}
        ${credHtml(an)}
        <div class="dif-foot">
          <div class="dif-prev" id="difPrev"></div>
          <div class="dif-e116" id="difE116" hidden>
            <div class="dif-k">Guia de ICMS (E116)</div>
            <p>O SPED não tem obrigação 000 e, com a correção, passa a haver ICMS a recolher. Informe a guia:</p>
            <label>Vencimento <input id="difVenc" placeholder="dd/mm/aaaa" value="${e116Qq.venc ? dt(e116Qq.venc) : ''}"></label>
            <label>Código de receita <input id="difCodRec" placeholder="ex.: 1210" value="${esc(e116Qq.cod_rec || '')}"></label>
          </div>
          <div class="dif-acts">
            <button class="act inv-export" id="btnDifAplicar" style="background:#e23d4c;color:#fff;border-color:transparent">Aplicar no SPED (gera arquivo novo)</button>
          </div>
        </div>
        <div id="difRes"></div>`;
      DIF.temE116 = !!e116;

      $('#btnDifFechar').addEventListener('click', () => { box.hidden = true; $('#corrSpedEmpty').hidden = false; });
      const anexar = async () => {
        const pick = await window.fiscocont.fiscal.pickXmlsFolder();
        if (pick.canceled || !pick.path) return;
        XMLS.path = pick.path; SN.an = null;
        await difalAbrir();
      };
      $('#btnDifXmls').addEventListener('click', anexar);
      if ($('#btnDifXmls2')) $('#btnDifXmls2').addEventListener('click', anexar);
      box.querySelectorAll('select[data-inter], input[data-interna], input[data-difal], input[data-cfop], input[data-rem], input[data-frete]').forEach((el) =>
        el.addEventListener('input', () => difalAtualiza()));
      box.querySelectorAll('select[data-classe]').forEach((el) => el.addEventListener('change', () => {
        DIF.classe = DIF.classe || {};
        DIF.classe[el.dataset.classe] = el.value;
        difalRender(); animaNumeros($('#corrDifal'));
        toast('Classificação alterada: confira as marcações da nota.');
      }));
      box.querySelectorAll('input[name="difBalcCfop"]').forEach((el) => el.addEventListener('change', () => {
        DIF.balcCfop = el.value;
        (an.docs || []).filter((d) => efe(d).status === 'balcao').forEach((d) => {
          const c = box.querySelector(`input[data-cfop="${d.id}"]`);
          if (c) c.checked = el.value === 'trocar';
        });
        box.querySelectorAll('.dif-bmodo label').forEach((l) => l.classList.toggle('on', !!l.querySelector('input:checked')));
        difalAtualiza();
      }));
      if (DIF.balcCfop === 'trocar') (an.docs || []).filter((d) => efe(d).status === 'balcao').forEach((d) => {
        const c = box.querySelector(`input[data-cfop="${d.id}"]`); if (c) c.checked = true;
      });
      const todos = $('#difTodos');
      if (todos) todos.addEventListener('change', () => { box.querySelectorAll('input[data-difal]').forEach((c) => { c.checked = todos.checked; }); difalAtualiza(); });
      box.querySelectorAll('input[data-cred], input[name="difCredModo"], #difCredCod').forEach((el) =>
        el.addEventListener('input', () => difalAtualiza()));
      const todosC = $('#difCredTodos');
      if (todosC) todosC.addEventListener('change', () => { box.querySelectorAll('input[data-cred]').forEach((c) => { c.checked = todosC.checked; }); difalAtualiza(); });
      $('#btnDifAplicar').addEventListener('click', difalAplicar);
      difalAtualiza();
    }

    // ---- compras no balcão em outro estado (Parecer 053/2019/GETRI/CRE/SEFIN-RO) ----
    function difBalcaoHtml(an) {
      const bs = (an.docs || []).filter((d) => d.balcao);
      if (!bs.length) return '';
      const credPor = {};
      ((an.creditos || {}).docs || []).forEach((c) => { credPor[c.id] = c; });
      const g = { rem: [0, 0], cred: [0, 0], ok: [0, 0], ativo: [0, 0], nfce: [0, 0] };
      bs.forEach((d) => {
        const ef = efe(d);
        if (d.balcao.mod === '65') { g.nfce[0]++; g.nfce[1] += d.grupos.reduce((t, x) => t + x.valor, 0); }
        else if (ef.classe === 'ativo') { g.ativo[0]++; g.ativo[1] += d.difal_calculado; }
        else if (d.difal_lancado > 0) { g.rem[0]++; g.rem[1] += d.difal_lancado; }
        else if (!credPor[d.id]) g.ok[0]++;
        if (credPor[d.id] && ef.classe !== 'ativo') { g.cred[0]++; g.cred[1] += credPor[d.id].credito; }
      });
      const mx = Math.max(1, ...Object.values(g).map((x) => x[0]));
      const barra = (t, k, cor, i) => g[k][0] ? `<div class="sn-bar" style="--i:${i}"><span class="sn-bl">${t}</span><span class="sn-bt"><i style="--w:${(g[k][0] / mx * 100).toFixed(1)}%;background:${cor}"></i></span><b>${g[k][0]}</b><small>${g[k][1] ? 'R$ ' + fm(g[k][1]) : '—'}</small></div>` : '';
      const trocar = DIF.balcCfop === 'trocar';
      const linhas = bs.map((d) => {
        const ef = efe(d), b = d.balcao, st = STATUS[ef.status] || [ef.status, 'b-mute'], cr = credPor[d.id];
        const sped = [];
        sped.push(`<span class="pill p-s">CFOP ${esc([...new Set(d.grupos.flatMap((x) => x.cfops))].join(', ') || (d.correcoes_cfop[0] || {}).de || '—')}</span>`);
        if (d.difal_lancado) sped.push(`DIFAL lançado <b>R$ ${fm(d.difal_lancado)}</b>`);
        if (cr) sped.push(`crédito R$ ${fm(cr.credito)} <i>(quadro de crédito)</i>`);
        if (b.mod === '65') sped.push('NFC-e escriturada no C100');
        const acao = b.mod === '65' ? 'Só aviso: NFC-e não entra na EFD de entradas'
          : ef.classe === 'ativo' ? (d.difal_lancado > 0 && ef.status === 'ok' ? 'Manter o DIFAL' : 'Lançar o DIFAL (marque na tabela abaixo)')
          : [d.difal_lancado > 0 ? 'Retirar o DIFAL' : '', cr ? 'retirar o crédito' : ''].filter(Boolean).join(' e ') || 'Nada a corrigir';
        return `<tr>
          <td><b>${esc(d.num)}</b><small>${dt(d.data)} · ${b.mod === '65' ? 'NFC-e 65' : 'NF-e 55'}</small></td>
          <td>${esc(d.fornecedor)}<small>${esc(d.uf_origem)}</small></td>
          <td><div class="dif-xs">${b.mod === '65' ? '<span class="pill p-x">NFC-e</span><span class="pill p-x">consumidor</span>'
            : `<span><span class="pill p-x">CFOP ${esc(b.cfop_xml.join(', ') || '—')}</span><span class="pill p-x">interna</span>${b.ind_pres === '1' ? '<span class="pill p-x">presencial</span>' : ''}</span>
               <span>${b.aliq_xml.length ? 'ICMS ' + b.aliq_xml.map((x) => fa(x)).join(' / ') + ' (alíquota interna da origem)' : ''}</span>`}</div></td>
          <td><div class="dif-xs">${sped.join('<br>')}</div></td>
          <td>${esc((b.itens || []).join(', ') || '—')}</td>
          <td>${b.mod === '65' ? 'Consumo imediato' : `<select class="dif-cls" data-classe="${d.id}">
              <option value="consumo" ${ef.classe === 'consumo' ? 'selected' : ''}>Consumo imediato / em trânsito</option>
              <option value="ativo" ${ef.classe === 'ativo' ? 'selected' : ''}>Bem do ativo (segue interestadual)</option></select>
              <small>${esc(b.motivo)}</small>`}</td>
          <td>${acao}</td>
          <td><span class="dif-b ${st[1]}">${st[0]}</span></td></tr>`;
      }).join('');
      return `
        <div class="dif-sec">
          <div class="dif-k">Compras no balcão em outro estado</div>
          <div class="dif-lei"><b>Regra da SEFIN/RO (Parecer 053/2019/GETRI/CRE):</b> compra feita no balcão em outro estado é <b>operação interna da origem</b>,
            com a alíquota interna de lá, e <b>não gera DIFAL para RO</b>. A NF-e entra no SPED <b>sem crédito</b>; a NFC-e não entra na EFD de entradas.
            <b>Exceção:</b> bem do ativo (o parecer cita motor, carroceria, eixo, conjunto de pneus, câmara frigorífica e furgão) segue interestadual e o DIFAL é devido.
            O sistema reconhece pelo XML: <b>destinatário com endereço em RO</b>, <b>fornecedor de outro estado</b> e <b>operação interna</b> (destino da operação = 1, CFOP 5.xxx).</div>
          <div class="sn-dash">
            <div class="sn-card"><div class="dif-k">Situação das compras de balcão</div><div class="sn-bars">
              ${barra('Retirar DIFAL lançado', 'rem', '#e34948', 0)}${barra('Retirar crédito tomado', 'cred', '#eb6834', 1)}
              ${barra('Correto (sem DIFAL e sem crédito)', 'ok', '#1baf7a', 2)}${barra('Bem do ativo · DIFAL devido', 'ativo', '#4a3aa7', 3)}
              ${barra('NFC-e na EFD (aviso)', 'nfce', '#eda100', 4)}</div></div>
            <div class="sn-card"><div class="dif-k">CFOP de entrada nas compras de balcão</div>
              <div class="dif-modo dif-bmodo">
                <label class="${trocar ? '' : 'on'}"><input type="radio" name="difBalcCfop" value="manter" ${trocar ? '' : 'checked'}> <b>Manter como está</b><br>O parecer não define o CFOP de entrada.</label>
                <label class="${trocar ? 'on' : ''}"><input type="radio" name="difBalcCfop" value="trocar" ${trocar ? 'checked' : ''}> <b>Trocar 2.xxx para 1.xxx</b><br>Trata a compra como interna no SPED.</label>
              </div>
              <p class="dif-sub" style="margin:0">A troca marca o CFOP de cada compra de balcão na tabela de notas; dá para desmarcar nota a nota.</p></div>
          </div>
          <div class="dif-tw"><table class="dif-tab">
            <thead><tr><th>Nota</th><th>Fornecedor</th><th>No XML (fornecedor)</th><th>No SPED (cliente)</th><th>Itens</th><th>Classificação</th><th>O que será feito</th><th>Situação</th></tr></thead>
            <tbody>${linhas}</tbody></table></div>
        </div>`;
    }

    // ---- DIFAL do frete (CT-e) de uso e consumo / ativo — mesmo código da mercadoria, no D197 ----
    function difFreteHtml(an) {
      const fs = an.fretes || [];
      if (!fs.length) return '';
      const linhas = fs.map((f) => {
        const st = STATUS[f.status] || [f.status, 'b-mute'];
        const pode = ['faltando', 'divergente'].includes(f.status) && f.difal_calculado > 0;
        return `<tr class="${pode ? '' : 'dif-off'}">
          <td>${pode ? `<input type="checkbox" data-frete="${f.id}" ${f.sugerido ? 'checked' : ''} title="Lançar o DIFAL do frete (D195/D197)">` : ''}</td>
          <td><b>${esc(f.num)}</b><small>${dt(f.data)} · CT-e</small></td>
          <td>${esc(f.transportadora)}<small>${esc(f.cnpj)}</small></td>
          <td><b>${esc(f.uf_ini)}</b> → ${esc(f.uf_fim || 'RO')}</td>
          <td>${f.nfes_sped} de ${f.nfes} no SPED<small>${esc((f.notas || []).join(', '))}</small></td>
          <td class="n">R$ ${fm(f.valor)}</td>
          <td>${f.grupos.map((g) => `<div>${g.tipo === 'ativo' ? 'Ativo' : 'Uso/consumo'} · ${fa(g.proporcao)} · R$ ${fm(g.valor)} · ${fa(g.aliq_inter)}<small>${esc(g.fonte_aliq)}</small></div>`).join('') || '—'}</td>
          <td class="n"><b>${f.difal_calculado ? 'R$ ' + fm(f.difal_calculado) : '—'}</b></td>
          <td class="n">${f.difal_lancado ? 'R$ ' + fm(f.difal_lancado) : '—'}</td>
          <td><span class="dif-b ${st[1]}">${st[0]}</span>${(f.obs || []).map((o) => `<small class="dif-obs">${esc(o)}</small>`).join('')}</td></tr>`;
      }).join('');
      return `
        <div class="dif-sec">
          <div class="dif-k">DIFAL do frete (CT-e) de uso e consumo e ativo</div>
          <div class="dif-lei"><b>Quando incide:</b> frete contratado pela empresa (tomador do CT-e), com transporte iniciado em outro estado e mercadoria de uso e consumo
            ou ativo (LC 87/96, art. 12, XIII). Usa o mesmo código da mercadoria (RO40000002 / RO40000001), lançado em <b>D195 + D197</b> no CT-e e somado no campo 03 do E110.
            Frete CIF (tomador = fornecedor) não entra: já está no valor da NF-e. Quando o CT-e leva também mercadoria de outra finalidade, o frete é rateado pelo valor das notas.</div>
          <div class="dif-tw"><table class="dif-tab">
            <thead><tr><th></th><th>CT-e</th><th>Transportadora</th><th>Trajeto</th><th>NF-e transportadas</th><th class="n">Frete</th><th>Parte de uso/ativo · alíquota</th>
              <th class="n">DIFAL</th><th class="n">Lançado</th><th>Situação</th></tr></thead>
            <tbody>${linhas}</tbody></table></div>
          ${(an.resumo || {}).ctes_sem_xml ? `<p class="dif-sub" style="margin:0">${an.resumo.ctes_sem_xml} CT-e de entrada sem XML anexado: não dá para saber o tomador nem as notas transportadas.</p>` : ''}
        </div>`;
    }

    // ---- XML × SPED: alíquota interestadual conferida item a item ----
    function difCompHtml(docs) {
      const cs = docs.filter((d) => d.comparacao);
      if (!cs.length) return '';
      const mx = Math.max(1, ...cs.flatMap((d) => [d.comparacao.difal_sped, d.comparacao.difal_xml]));
      const al = (a) => a.length ? a.map((x) => fa(x)).join(' + ') : '—';
      return `
        <div class="dif-sec">
          <div class="dif-k">Alíquota do XML × alíquota deduzida pelo SPED</div>
          <p class="dif-sub" style="margin:0">Notas em que o XML do fornecedor muda a alíquota interestadual ou o valor do DIFAL (produto importado a 4%, itens com alíquotas diferentes, IPI e despesas na base, ICMS-ST retido). O cálculo da tabela abaixo já usa o XML.</p>
          <div class="dif-tw"><table class="dif-tab">
            <thead><tr><th>Nota</th><th>Fornecedor</th><th>UF</th><th>Origem (XML)</th><th class="n">Alíq. pelo SPED</th><th class="n">Alíq. pelo XML</th>
              <th class="n">DIFAL pelo SPED</th><th class="n">DIFAL pelo XML</th><th class="n">Diferença</th><th>Comparação</th></tr></thead>
            <tbody>${cs.map((d, i) => {
              const c = d.comparacao, df = r2(c.difal_xml - c.difal_sped);
              return `<tr>
                <td><b>${esc(d.num)}</b><small>${dt(d.data)}</small></td><td>${esc(d.fornecedor)}</td><td><b>${esc(d.uf_origem)}</b></td>
                <td>${esc((c.origens || []).join(', ') || '—')}</td>
                <td class="n">${al(c.aliq_sped)}</td><td class="n"><b>${al(c.aliq_xml)}</b></td>
                <td class="n">R$ ${fm(c.difal_sped)}</td><td class="n"><b>R$ ${fm(c.difal_xml)}</b></td>
                <td class="n ${df >= 0 ? 'dif-mais' : 'dif-menos'}">${df >= 0 ? '+' : '−'} R$ ${fm(Math.abs(df))}</td>
                <td class="dif-cmp" style="--i:${i}"><i class="a" style="--w:${(c.difal_sped / mx * 100).toFixed(1)}%"></i><i class="d" style="--w:${(c.difal_xml / mx * 100).toFixed(1)}%"></i></td>
              </tr>`;
            }).join('')}</tbody>
          </table></div>
          <div class="sn-leg"><span><i style="background:#c9cfdc"></i>pelo SPED</span><span><i style="background:#1f2a5a"></i>pelo XML</span></div>
        </div>`;
    }

    // ---- crédito de ICMS tomado em uso e consumo / ativo (LC 87/96, art. 33, I; art. 20, § 5º) ----
    function credHtml(an) {
      const cr = an.creditos || { docs: [], codigos_estorno: [] }, cd = cr.docs || [];
      const ro = (an.empresa || {}).uf;
      const nUso = cd.filter((x) => x.sugerido).length, nAt = cd.length - nUso;
      const tAt = r2(cd.filter((x) => !x.sugerido).reduce((t, x) => t + x.credito, 0));
      const v = (a, b) => `<span class="v-old">${a}</span><span class="v-new">${b}</span>`;
      const linhas = cd.map((x) => {
        const it = x.itens.length
          ? x.itens.map((i) => `${esc(i.descr || i.item)}`).join('<br>')
          : '<span class="dif-mute">nota sem itens (resumo C190)</span>';
        const g = x.c190;
        return `
          <tr data-cid="${x.id}">
            <td><input type="checkbox" data-cred="${x.id}" ${x.sugerido ? 'checked' : ''}></td>
            <td><b>${esc(x.num)}</b><small>${dt(x.data)}</small></td>
            <td>${esc(x.fornecedor)}<small>${esc(x.cnpj)}</small></td>
            <td><b>${esc(x.uf_origem || '?')}</b></td>
            <td>${g.map((c) => c.cfop).join('<br>')}</td>
            <td>${it}</td>
            <td>${g.map((c) => c.cst).join('<br>')}</td>
            <td class="n">${g.map((c) => 'R$ ' + fm(c.vl_opr)).join('<br>')}</td>
            <td class="n">${g.map((c) => v(fm(c.bc), '0,00')).join('<br>')}</td>
            <td class="n">${g.map((c) => v(fa(c.aliq), '0%')).join('<br>')}</td>
            <td class="n">${g.map((c) => v(fm(c.icms), '0,00')).join('<br>')}<span class="v-est">estornado no E111</span></td>
            <td><span class="dif-b ${x.sugerido ? 'b-err' : 'b-warn'}">${x.sugerido ? 'Crédito indevido' : (x.tipo === 'ativo' ? 'Ativo · conferir CIAP' : 'Conferir')}</span>
              ${x.difal_lancado ? `<small class="dif-obs">DIFAL lançado: R$ ${fm(x.difal_lancado)} (não muda)</small>` : ''}
              ${(x.obs || []).map((o) => `<small class="dif-obs">${esc(o)}</small>`).join('')}</td>
          </tr>`;
      }).join('');
      const cods = cr.codigos_estorno || [];
      return `
        <div class="dif-sec">
          <div class="dif-sec-h"><div class="dif-k">Crédito de ICMS em uso e consumo e ativo</div></div>
          <div class="dif-lei"><b>Por que isso é corrigido:</b> material de uso e consumo só dá direito a crédito de ICMS a partir de 01/01/2033
            (LC 87/96, art. 33, I). No ativo imobilizado o crédito é apropriado em 48 parcelas pelo CIAP (art. 20, § 5º), não direto na nota.
            Crédito tomado na nota reduz indevidamente o ICMS a recolher.</div>
          ${cd.length ? `
          <div class="dif-kpis">
            <div class="k-err"><span>Uso e consumo com crédito</span><b data-n="${nUso}">0</b><small>R$ ${fm(cr.total_uso)}</small></div>
            <div class="k-warn"><span>Ativo com crédito na nota</span><b data-n="${nAt}">0</b><small>R$ ${fm(tAt)} · conferir o CIAP</small></div>
            <div><span>Crédito tomado (total)</span><b data-n="${cr.total || 0}" data-fmt="brl">R$ 0,00</b></div>
          </div>
          <div class="dif-modo">
            <label class="on"><input type="radio" name="difCredModo" value="zerar" checked> <b>Zerar o crédito na nota</b>
              Zera base, alíquota e ICMS dos itens (C170), refaz o C190 e o total da nota (C100). O total de créditos do E110 (campo 06) diminui. <span class="dif-tag">recomendado</span></label>
            <label><input type="radio" name="difCredModo" value="estorno" ${cods.length ? '' : 'disabled'}> <b>Manter a nota e estornar no E111</b>
              A nota fica como veio e entra um estorno de crédito no E111 (campo 05 do E110).
              ${cods.length ? `<select id="difCredCod">${cods.map((c) => `<option value="${c.cod}" ${c.cod === cr.cod_estorno_padrao ? 'selected' : ''}>${c.cod} · ${esc(c.descr.slice(0, 90))}</option>`).join('')}</select>`
                : `<small>Sem tabela de códigos de ajuste para ${esc(ro || 'esta UF')}.</small>`}</label>
          </div>
          <div class="dif-tw"><table class="dif-tab dif-cred">
            <thead><tr><th><input type="checkbox" id="difCredTodos" title="Marcar/desmarcar todas"></th><th>Nota</th><th>Fornecedor</th><th>UF</th><th>CFOP</th><th>Item</th><th>CST</th>
              <th class="n">Valor</th><th class="n">Base</th><th class="n">Alíq.</th><th class="n">ICMS creditado</th><th>Situação</th></tr></thead>
            <tbody>${linhas}</tbody>
          </table></div>` : '<div class="dif-av ok">Nenhuma nota de uso e consumo ou ativo com crédito de ICMS tomado neste SPED.</div>'}
        </div>`;
    }

    function credSelecao() {
      const an = DIF.an, box = $('#corrDifal'), cd = (an.creditos || {}).docs || [];
      const m = box.querySelector('input[name="difCredModo"]:checked');
      const modo = m ? m.value : 'zerar';
      box.querySelectorAll('.dif-modo label').forEach((l) => l.classList.toggle('on', !!l.querySelector('input:checked')));
      const ids = [];
      let total = 0;
      for (const x of cd) {
        const c = box.querySelector(`input[data-cred="${x.id}"]`);
        const on = !!(c && c.checked);
        const tr = box.querySelector(`tr[data-cid="${x.id}"]`);
        if (tr) { tr.classList.toggle('z', on && modo === 'zerar'); tr.classList.toggle('es', on && modo === 'estorno'); }
        if (on) { ids.push(x.id); total += x.credito; }
      }
      const codEl = $('#difCredCod');
      return { modo, ids, total: r2(total), cod: codEl ? codEl.value : '' };
    }

    function difalSelecao() {
      const an = DIF.an, box = $('#corrDifal'), sel = [];
      let delta = 0, nCfop = 0, nDif = 0, nRem = 0;
      for (const d of an.docs || []) {
        const cCfop = box.querySelector(`input[data-cfop="${d.id}"]`);
        const cDif = box.querySelector(`input[data-difal="${d.id}"]`);
        const corrigir = !!(cCfop && cCfop.checked), incluir = !!(cDif && cDif.checked);
        const grupos = [];
        let tot = 0;
        d.grupos.forEach((g, gi) => {
          const row = box.querySelector(`.dif-g[data-doc="${d.id}"][data-g="${gi}"]`);
          const inter = Number(row.querySelector('[data-inter]').value);
          const interna = Number(String(row.querySelector('[data-interna]').value).replace(',', '.'));
          const c = difCalc(g.valor, inter, interna, d.base_dupla ?? an.base_dupla);
          row.querySelector('[data-val]').textContent = d.interestadual && efe(d).status !== 'balcao' ? 'R$ ' + fm(c.difal) : '—';
          tot += c.difal;
          grupos.push({ tipo: g.tipo, aliq_inter: g.aliq_inter, aliq_inter_nova: inter, aliq_interna: interna });
        });
        const cRem = box.querySelector(`input[data-rem="${d.id}"]`);
        const rem = !!(cRem && cRem.checked);
        if (rem) { delta -= d.difal_lancado || 0; nRem++; }
        if (incluir) { delta += tot - (d.difal_lancado || 0); nDif++; }
        if (corrigir) nCfop++;
        if (rem) sel.push({ id: d.id, corrigir_cfop: corrigir, remover_difal: true, grupos: [] });
        else if (corrigir || incluir) sel.push({ id: d.id, corrigir_cfop: corrigir, incluir_difal: incluir, grupos });
      }
      const fretes = [];
      let nFrete = 0, vFrete = 0;
      for (const f of an.fretes || []) {
        const c = box.querySelector(`input[data-frete="${f.id}"]`);
        if (!c || !c.checked) continue;
        nFrete++; vFrete += f.difal_calculado - (f.difal_lancado || 0);
        delta += f.difal_calculado - (f.difal_lancado || 0);
        fretes.push({ id: f.id, incluir: true, grupos: f.grupos.map((g) => ({ tipo: g.tipo, aliq_inter: g.aliq_inter, aliq_interna: g.aliq_interna })) });
      }
      return { sel, fretes, delta: r2(delta), nCfop, nDif, nRem, nFrete, vFrete: r2(vFrete), cred: credSelecao() };
    }

    // prévia do E110 pelas fórmulas do Guia Prático (campos 11, 13 e 14)
    function difalAtualiza() {
      const an = DIF.an, e = an.e110, { delta, nCfop, nDif, nRem, nFrete, cred } = difalSelecao();
      const prev = $('#difPrev');
      const nCred = cred.ids.length;
      const b = $('#btnDifAplicar');
      b.disabled = !(nCfop || nDif || nCred || nRem || nFrete);
      b.dataset.conf = '';
      b.textContent = 'Aplicar no SPED (gera arquivo novo)';
      if (!e) { prev.innerHTML = '<div class="dif-av err">SPED sem registro E110: o DIFAL e o crédito não podem ser lançados (só a troca de CFOP).</div>'; return; }
      const calc = (aj, est, cr) => {
        const expr = (e.deb + aj + e.tot_aj_deb + est) - (cr + e.aj_cred + e.tot_aj_cred + e.est_deb + e.sld_ant);
        const sa = Math.max(0, expr);
        return { aj, est, cr, sa, rec: Math.max(0, sa - e.ded), cred: Math.max(0, -(expr - e.ded)) };
      };
      const est = cred.modo === 'estorno' ? cred.total : 0, menos = cred.modo === 'zerar' ? cred.total : 0;
      const A = calc(e.aj_deb, e.est_cred, e.cred), D = calc(r2(e.aj_deb + delta), r2(e.est_cred + est), r2(e.cred - menos));
      const lin = (t, a, b) => `<tr><td>${t}</td><td class="n">R$ ${fm(a)}</td><td class="n ${r2(a) !== r2(b) ? 'mud' : ''}">R$ ${fm(b)}</td></tr>`;
      prev.innerHTML = `
        <div class="dif-k">Conferência da apuração (E110) com o que está marcado</div>
        <p class="dif-sub">${nCfop} nota(s) com CFOP a corrigir · ${nDif} nota(s) com DIFAL a lançar${nFrete ? ` · ${nFrete} CT-e com DIFAL do frete` : ''}${nRem ? ` · ${nRem} compra(s) de balcão com DIFAL retirado` : ''} · diferença no campo 03: R$ ${fm(delta)} ·
          ${nCred} nota(s) com crédito ${cred.modo === 'zerar' ? 'zerado' : 'estornado'} (<b>R$ ${fm(cred.total)}</b>)</p>
        <table class="dif-mini"><thead><tr><th></th><th class="n">Antes</th><th class="n">Depois</th></tr></thead><tbody>
          ${lin('Ajustes a débito das notas (campo 03)', A.aj, D.aj)}
          ${lin('Estornos de crédito (campo 05)', A.est, D.est)}
          ${lin('Créditos das notas (campo 06)', A.cr, D.cr)}
          ${lin('Saldo devedor (campo 11)', A.sa, D.sa)}
          ${lin('ICMS a recolher (campo 13)', A.rec, D.rec)}
          ${lin('Saldo credor a transportar (campo 14)', A.cred, D.cred)}
        </tbody></table>
        ${r2(A.cred) !== r2(D.cred) ? '<p class="dif-warn">O saldo credor muda: o SPED do mês seguinte terá de receber o novo saldo credor anterior.</p>' : ''}`;
      DIF.precisaE116 = !DIF.temE116 && r2(D.rec) > 0 && r2(D.rec) !== r2(A.rec);
      $('#difE116').hidden = !DIF.precisaE116;
    }

    async function difalAplicar() {
      const b = $('#btnDifAplicar');
      const { sel, fretes, delta, nCfop, nDif, nRem, nFrete, vFrete, cred } = difalSelecao();
      if (!sel.length && !cred.ids.length && !fretes.length) return;
      const selecao = { docs: sel, fretes };
      if (cred.ids.length) selecao.creditos = { modo: cred.modo, cod_aj: cred.cod, docs: cred.ids };
      if (DIF.precisaE116) {
        const venc = ($('#difVenc').value || '').replace(/\D/g, ''), cod = ($('#difCodRec').value || '').trim();
        if (venc.length !== 8 || !cod) { toast('Informe o vencimento (dd/mm/aaaa) e o código de receita da guia.', true); return; }
        selecao.e116 = { venc, cod_rec: cod };
      }
      if (b.dataset.conf !== '1') {
        b.dataset.conf = '1';
        const partes = [];
        if (nCfop) partes.push(`${nCfop} CFOP`);
        if (nDif || nRem || nFrete) partes.push(`campo 03 ${delta >= 0 ? '+' : '−'} R$ ${fm(Math.abs(delta))}`);
        if (nFrete) partes.push(`${nFrete} CT-e (R$ ${fm(vFrete)})`);
        if (nRem) partes.push(`${nRem} balcão sem DIFAL`);
        if (cred.ids.length) partes.push(`${cred.modo === 'zerar' ? 'retirar' : 'estornar'} R$ ${fm(cred.total)} de crédito`);
        b.textContent = `Confirmar: ${partes.join(' · ')} (gera arquivo novo)`;
        return;
      }
      overlay(true, 'Lançando no SPED e recalculando E110, E116 e Bloco 9…');
      const res = await window.fiscocont.admin.difalAplicar({ spedPath: corrSpedPath, usarCorrigido: corrFeito, selecao, xmls: XMLS.path });
      overlay(false);
      b.dataset.conf = ''; b.textContent = 'Aplicar no SPED (gera arquivo novo)';
      if (res.error) { toast(res.error, true); return; }
      corrFeito = true;
      const r = res.resumo || {};
      const ea = r.e110_antes, ed = r.e110_depois;
      $('#difRes').innerHTML = `
        <div class="dif-done">
          <div class="dif-k">Lançado — arquivo novo gerado (o original não foi alterado)</div>
          <div class="dif-kpis">
            <div><span>CFOP corrigidos</span><b data-n="${r.cfop_corrigidos || 0}">0</b><small>em ${r.notas_cfop ?? 0} nota(s) · C170 e C190</small></div>
            <div><span>Notas com DIFAL</span><b data-n="${r.difal_incluidos || 0}">0</b><small>${r.c195_inseridos ?? 0} C195 · ${r.c197_inseridos ?? 0} C197</small></div>
            ${r.fretes_incluidos ? `<div class="k-err"><span>DIFAL do frete (D197)</span><b data-n="${r.frete_difal || 0}" data-fmt="brl">R$ 0,00</b><small>${r.fretes_incluidos} CT-e · ${r.d197_inseridos || 0} D197</small></div>` : ''}
            ${r.notas_balcao_retiradas ? `<div class="k-ok"><span>DIFAL retirado (balcão)</span><b data-n="${r.difal_retirado_balcao || 0}" data-fmt="brl">R$ 0,00</b><small>${r.notas_balcao_retiradas} nota(s) · Parecer 053/2019</small></div>` : ''}
            <div class="k-err"><span>DIFAL lançado</span><b data-n="${r.difal_total || 0}" data-fmt="brl">R$ 0,00</b>${r.difal_removido ? `<small>substituiu R$ ${fm(r.difal_removido)} anterior</small>` : ''}</div>
            ${r.cred_notas ? `<div class="k-err"><span>Crédito ${r.cred_modo === 'zerar' ? 'retirado' : 'estornado'}</span><b data-n="${r.cred_total || 0}" data-fmt="brl">R$ 0,00</b><small>${r.cred_notas} nota(s)${r.cred_modo === 'zerar' ? ` · ${r.cred_c170} C170 · ${r.cred_c190} C190` : ' · E111'}</small></div>` : ''}
            ${ea && ed ? `<div><span>ICMS a recolher</span><b>R$ ${fm(ed.recolher)}</b><small>antes R$ ${fm(ea.recolher)}</small></div>` : ''}
          </div>
          ${r.cred_e111 ? `<p class="dif-sub">${esc(r.cred_e111)}</p>` : ''}
          ${r.e116 ? `<p class="dif-sub">${esc(r.e116)}</p>` : ''}
          ${(r.obs_0460_criados || []).length ? `<p class="dif-sub">Observação 0460 criada: ${r.obs_0460_criados.map(esc).join(', ')}</p>` : ''}
          ${(r.avisos || []).length ? `<div class="dif-av"><ul>${r.avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
          <div class="dif-acts">
            <button class="act inv-export" id="btnDifVer">Ver todos os dados (corrigido)</button>
            <button class="act inv-export" id="btnDifReconf">Conferir de novo</button>
            <button class="act inv-export" id="btnDifBaixar" style="background:#0ea472;color:#fff;border-color:transparent">Baixar SPED corrigido</button>
          </div>
        </div>`;
      $('#btnDifBaixar').addEventListener('click', async () => {
        const r3 = await window.fiscocont.fiscal.baixarSpedCorrigido();
        if (r3.canceled) return;
        if (r3.error) { toast(r3.error, true); return; }
        toast('SPED corrigido salvo.');
        window.fiscocont.openPath(r3.path);
      });
      $('#btnDifVer').addEventListener('click', async () => {
        overlay(true, 'Lendo todos os dados do SPED corrigido…');
        const r2_ = await window.fiscocont.fiscal.visualizarSpedCorrigido();
        overlay(false);
        if (r2_.error) { toast(r2_.error, true); return; }
        const fr = $('#corrSpedFrame'); fr.srcdoc = r2_.html; fr.hidden = false;
        fr.scrollIntoView({ behavior: 'smooth' });
      });
      $('#btnDifReconf').addEventListener('click', () => difalAbrir());
      animaNumeros($('#difRes'));
      $('#difRes').scrollIntoView({ behavior: 'smooth' });
      toast('DIFAL lançado. Confira e baixe o SPED corrigido.');
    }

    // ---- números que "contam" até o valor (dashboard animado) ----
    function animaNumeros(root) {
      if (!root) return;
      root.querySelectorAll('[data-n]').forEach((el) => {
        const alvo = Number(el.dataset.n) || 0, tipo = el.dataset.fmt || 'int';
        const fmtv = (v) => tipo === 'brl' ? 'R$ ' + fm(v) : Math.round(v).toLocaleString('pt-BR');
        const t0 = performance.now(), dur = 900;
        const passo = (t) => {
          const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
          el.textContent = fmtv(alvo * e);
          if (k < 1) requestAnimationFrame(passo); else el.textContent = fmtv(alvo);
        };
        requestAnimationFrame(passo);
      });
    }

    // =====================================================================
    // Crédito de fornecedor do Simples Nacional — C195 + C197 RO00000001 (só Admin)
    // SEFIN/RO, IN 017/2016 (Tabela 5.3 e manual da EFD, item 19); LC 123/2006, art. 23, §§ 1º a 5º
    // =====================================================================
    // ---- ICMS creditado no SPED × ICMS destacado no XML da entrada (pedido do Rafael, 19/10) ----
    const IX = { an: null, origem: null, sel: new Set() };
    const IX_ST = {
      sem_destaque: ['Crédito sem destaque na nota', 'b-err', '#e34948'],
      maior: ['Crédito maior que o destacado', 'b-err', '#f08c3a'],
      maior_sem_item: ['Diferença fora dos itens', 'b-warn', '#eda100'],
      st_sem_retencao: ['Escriturado como ST, nota sem ST', 'b-warn', '#4f46e5'],
      menor: ['Crédito menor que o destacado', 'b-mute', '#7c8bd6'],
    };
    function ixFechar() { $('#corrIcmsXml').hidden = true; $('#corrValXml').hidden = true; $('#corrEstST').hidden = true; $('#corrSpedEmpty').hidden = false; }
    async function ixAbrir() {
      if (!corrSpedPath) return;
      ['#corrSpedEmpty', '#corrSpedFrame', '#corrSpedResumo', '#corrDifal', '#corrSimples', '#corrLote', '#corrValXml', '#corrEstST'].forEach((s) => { const el = $(s); if (el) el.hidden = true; });
      const box = $('#corrIcmsXml');
      box.hidden = false;
      if (!XMLS.path) { ixVazio(); return; }
      await ixAnalisar();
    }
    function ixVazio() {
      const box = $('#corrIcmsXml');
      box.innerHTML = `
        <div class="dif-head"><div>
          <div class="dif-k">Corretor do SPED · Admin · ICMS creditado × ICMS da nota</div>
          <h3>Selecione os XMLs de entrada do período</h3>
          <div class="dif-sub">Cada nota de entrada é cruzada pela chave de acesso com o XML, item a item.</div>
        </div><button class="act inv-export" id="btnIxFechar">Fechar</button></div>
        <div class="sn-vazio"><p>Anexe a pasta ou os <b>.zip</b> com os XMLs das notas de entrada.</p>
          <button class="act inv-export sn-big" id="btnIxXmls">Selecionar XMLs</button></div>`;
      $('#btnIxFechar').addEventListener('click', ixFechar);
      $('#btnIxXmls').addEventListener('click', ixEscolherXmls);
    }
    async function ixEscolherXmls() {
      const pick = await window.fiscocont.fiscal.pickXmlsFolder();
      if (pick.canceled || !pick.path) return;
      XMLS.path = pick.path;
      await ixAnalisar();
    }
    async function ixAnalisar() {
      overlay(true, 'Cruzando o ICMS creditado no SPED com o ICMS destacado nos XMLs…');
      const res = await window.fiscocont.admin.icmsXmlAnalisar({ spedPath: corrSpedPath, usarCorrigido: corrFeito, xmls: XMLS.path });
      overlay(false);
      if (res.error) { toast(res.error, true); if (!IX.an) ixVazio(); return; }
      IX.an = res.res; IX.origem = res.origem;
      IX.sel = new Set((IX.an.docs || []).filter((d) => d.sugerido).map((d) => d.id));
      ixRender();
    }
    function ixPrev() {
      const an = IX.an, e = an.e110 || {};
      const red = (an.docs || []).filter((d) => IX.sel.has(d.id)).reduce((t, d) => t + d.reducao, 0);
      const cred = e.cred || 0, rec = e.recolher || 0, sld = e.sld_transp || 0;
      const credD = Math.max(0, cred - red);
      const recD = sld > 0 ? Math.max(0, red - sld) + rec : rec + red;
      const sldD = Math.max(0, sld - red);
      $('#ixPrev').innerHTML = `<table class="dif-mini"><thead><tr><th></th><th class="n">Antes</th><th class="n">Depois</th></tr></thead><tbody>
        <tr><td>Créditos (E110, campo 06)</td><td class="n">R$ ${fm(cred)}</td><td class="n mud">R$ ${fm(credD)}</td></tr>
        <tr><td>Saldo credor a transportar</td><td class="n">R$ ${fm(sld)}</td><td class="n">R$ ${fm(sldD)}</td></tr>
        <tr><td><b>ICMS a recolher</b></td><td class="n">R$ ${fm(rec)}</td><td class="n"><b>R$ ${fm(recD)}</b></td></tr></tbody></table>
        <div class="dif-sub" style="margin-top:6px">Crédito retirado com o que está marcado: <b>R$ ${fm(red)}</b></div>`;
      $('#btnIxAplicar').disabled = !IX.sel.size;
      $('#ixE116').hidden = !(recD > 0 && !(an.e116 || []).some((g) => g.cod === '000'));
    }
    function ixLinha(d) {
      const st = IX_ST[d.status] || ['', 'b-mute', '#999'];
      const itens = (d.itens || []).map((i) => `<tr><td>${esc(i.num)}</td><td>${esc(i.descr)}<small>XML: ${esc(i.xprod)} · NCM ${esc(i.ncm)}</small></td><td>${esc(i.cfop)}</td>
        <td><span class="dif-b ${i.status === 'menor' ? 'b-mute' : i.status === 'st_sem_retencao' ? 'b-warn' : 'b-err'}">${esc(i.cst_sped)}</span> → ${esc(i.cst_xml)}</td>
        <td class="n">${fa(i.aliq_sped)} → ${fa(i.aliq_xml)}</td><td class="n">R$ ${fm(i.bc_sped)} → R$ ${fm(i.bc_xml)}</td>
        <td class="n"><b>R$ ${fm(i.icms_sped)}</b> → R$ ${fm(i.icms_xml)}</td></tr>`).join('');
      return `<tr class="${d.sugerido ? '' : 'dif-off'}">
        <td><label class="dif-ck"><input type="checkbox" class="ix-ck" data-id="${d.id}" ${IX.sel.has(d.id) ? 'checked' : ''} ${d.sugerido ? '' : 'disabled'}> <b>${esc(d.num)}</b></label><small>${dt(d.data)}</small></td>
        <td>${esc(d.fornecedor)}${d.simples ? ' <span class="dif-b b-warn">Simples</span>' : ''}<small>${esc(d.cnpj)} · ${esc(d.uf || '')}</small></td>
        <td>${(d.csts_xml || []).map(esc).join(', ') || '—'}<small>alíq. no SPED: ${(d.aliqs_sped || []).map(fa).join(', ') || '—'}</small></td>
        <td class="n">R$ ${fm(d.icms_xml)}</td><td class="n"><b>R$ ${fm(d.icms_sped)}</b></td>
        <td class="n"><b style="color:${d.reducao > 0 ? '#b3261e' : 'inherit'}">${d.reducao > 0 ? '− R$ ' + fm(d.reducao) : '—'}</b></td>
        <td style="white-space:normal;max-width:360px"><span class="dif-b ${st[1]}">${st[0]}</span>${(d.obs || []).map((o) => `<small style="white-space:normal">${esc(o)}</small>`).join('')}</td></tr>
        ${itens ? `<tr class="ix-det"><td colspan="7"><details class="mono-ex" style="margin:0"><summary>ver os ${d.itens.length} item(ns) com diferença${d.itens_ajuste ? ` · mais ${d.itens_ajuste} só com base/CST ajustados` : ''}</summary>
          <table class="dif-tab" style="margin-top:6px"><thead><tr><th>Item</th><th>Produto no SPED / no XML</th><th>CFOP</th><th>CST SPED → XML</th><th class="n">Alíquota</th><th class="n">Base</th><th class="n">ICMS</th></tr></thead><tbody>${itens}</tbody></table></details></td></tr>` : ''}`;
    }
    function ixRender() {
      const an = IX.an, emp = an.empresa || {}, rs = an.resumo || {}, box = $('#corrIcmsXml'), docs = an.docs || [];
      const e116 = (an.e116 || []).find((g) => g.cod === '000') || (an.e116 || [])[0] || {};
      box.innerHTML = `
        <div class="dif-head"><div>
          <div class="dif-k">Corretor do SPED · Admin · ICMS creditado × ICMS da nota</div>
          <h3>${esc(emp.nome || '')}</h3>
          <div class="dif-sub">CNPJ ${esc(emp.cnpj || '')} · período ${dt(emp.dt_ini)} a ${dt(emp.dt_fin)} · arquivo <b>${IX.origem === 'corrigido' ? 'já corrigido nesta sessão' : 'original'}</b> · ${rs.xml_lidos ?? 0} XMLs lidos</div>
        </div>
        <div class="sn-hbtn"><button class="act inv-export" id="btnIxXmls">Trocar XMLs</button><button class="act inv-export" id="btnIxFechar">Fechar</button></div></div>
        <div class="dif-kpis">
          <div><span>Notas conferidas</span><b data-n="${rs.notas_conferidas || 0}">0</b><small>${rs.notas_sem_xml ?? 0} entrada(s) sem XML${rs.sem_xml_com_credito ? ` · ${rs.sem_xml_com_credito} com crédito` : ''}</small></div>
          <div class="k-err"><span>Crédito acima da nota</span><b data-n="${(rs.sem_destaque || 0) + (rs.maior || 0) + (rs.maior_sem_item || 0)}">0</b><small>${rs.sem_destaque || 0} sem destaque (${rs.simples_com_credito || 0} do Simples) · ${rs.maior || 0} acima</small></div>
          <div class="k-err"><span>Crédito a retirar</span><b data-n="${rs.credito_corrigivel || 0}" data-fmt="brl">R$ 0,00</b><small>diferença total R$ ${fm(rs.credito_indevido)}</small></div>
          <div class="k-warn"><span>Escriturado como ST, nota sem ST</span><b data-n="${rs.st_sem_retencao || 0}">0</b><small>ICMS da nota não creditado: R$ ${fm(rs.st_sem_retencao_valor)}</small></div>
          <div><span>Crédito menor que a nota</span><b data-n="${rs.menor || 0}">0</b><small>só informativo · R$ ${fm(rs.credito_nao_tomado)}</small></div>
        </div>
        ${docs.length ? `
        ${rs.st_sem_retencao ? `<div class="dif-av"><b>Escriturado como ST, nota sem ST (${rs.st_sem_retencao} nota(s), R$ ${fm(rs.st_sem_retencao_valor)}):</b>
          itens lançados com CST 060 no SPED vieram na nota tributados normalmente, sem ICMS-ST retido. Se o produto é de substituição tributária em RO,
          falta recolher o ICMS-ST na entrada (antecipação); se não é, o ICMS destacado na nota não foi creditado. Essas notas não são corrigidas automaticamente.</div>` : ''}
        <div class="mono-card"><div class="dif-k">Notas com diferença — marque o que corrigir</div>
          <div class="dif-tw" style="margin-top:8px;max-height:620px"><table class="dif-tab"><thead><tr><th>Nota</th><th>Fornecedor</th><th>CST no XML</th><th class="n">ICMS na nota</th><th class="n">Creditado no SPED</th><th class="n">Corrigir</th><th>Situação</th></tr></thead>
          <tbody>${docs.map(ixLinha).join('')}</tbody></table></div></div>
        <div class="mono-grid">
          <div class="mono-card"><div class="dif-k">Apuração (E110) antes × depois</div><div id="ixPrev"></div></div>
          <div class="mono-card">
            <div class="dif-e116" id="ixE116" hidden style="margin-top:10px"><div class="dif-sub"><b>A empresa passa a ter ICMS a recolher e o SPED não tem guia (E116):</b></div>
              <label>Vencimento <input id="ixVenc" placeholder="dd/mm/aaaa" value="${e116.venc ? dt(e116.venc) : ''}"></label>
              <label>Código de receita <input id="ixCodRec" placeholder="ex.: 1210" value="${esc(e116.cod_rec || '')}"></label></div>
            <div class="dif-sub" style="margin-top:10px"><b>O que o arquivo novo muda:</b> nos itens marcados, base, alíquota e ICMS do C170 vão para o que o XML destaca (nota isenta: zera e leva o CST do XML),
              o C190 da nota é refeito por CST/CFOP/alíquota, o C100 recebe os novos totais, o campo 06 do E110 diminui, o E116 é ajustado e o Bloco 9 recontado.
              Nota de fornecedor do Simples sai sem crédito no C190 (o crédito permitido vai depois pelo botão Crédito Simples Nacional). Uso e consumo/ativo e ajustes em C197 não são mexidos. O original nunca é alterado.</div>
            <div class="dif-sub">Base legal: o crédito é o imposto cobrado e destacado na nota da operação anterior (LC 87/96, arts. 19, 20 e 23).</div>
            <div class="dif-acts"><button class="act inv-export" id="btnIxAplicar" style="background:#e23d4c;color:#fff;border-color:transparent">Aplicar no SPED (gera arquivo novo)</button></div>
          </div>
        </div>
        <div id="ixRes"></div>` : `<div class="dif-av ok">O ICMS creditado no SPED bate com o destacado nos XMLs em todas as ${rs.notas_conferidas || 0} nota(s) conferidas.</div>`}
        ${(an.sem_xml_credito || []).length ? `<div class="mono-card"><details class="mono-ex" style="margin:0" ${docs.length ? '' : 'open'}><summary>Entradas com crédito de ICMS e <b>sem XML</b> para conferir — ${an.sem_xml_credito.length} nota(s), R$ ${fm(rs.sem_xml_credito_valor)}</summary>
          <div class="dif-sub" style="margin:6px 0">Anexe os XMLs dessas notas (Trocar XMLs) para o sistema conferir o destaque.</div>
          <div class="dif-tw" style="max-height:360px"><table class="dif-tab"><thead><tr><th>Nota</th><th>Fornecedor</th><th>Chave de acesso</th><th class="n">ICMS creditado no SPED</th></tr></thead>
          <tbody>${an.sem_xml_credito.map((z) => `<tr><td><b>${esc(z.num)}</b><small>${dt(z.data)}</small></td><td>${esc(z.fornecedor)}<small>${esc(z.cnpj)}</small></td><td style="font-family:monospace;font-size:11.5px">${esc(z.chave)}</td><td class="n">R$ ${fm(z.icms_sped)}</td></tr>`).join('')}</tbody></table></div></details></div>` : ''}`;
      animaNumeros(box);
      $('#btnIxFechar').addEventListener('click', ixFechar);
      $('#btnIxXmls').addEventListener('click', ixEscolherXmls);
      if (!docs.length) return;
      box.querySelectorAll('.ix-ck').forEach((c) => c.addEventListener('change', () => { const id = Number(c.dataset.id); c.checked ? IX.sel.add(id) : IX.sel.delete(id); ixPrev(); }));
      ixPrev();
      $('#btnIxAplicar').addEventListener('click', ixAplicar);
    }
    async function ixAplicar() {
      const selecao = { docs: [...IX.sel] };
      if (!$('#ixE116').hidden) {
        const venc = ($('#ixVenc').value || '').replace(/\D/g, ''), cod = ($('#ixCodRec').value || '').trim();
        if (venc.length !== 8 || !cod) { toast('Informe o vencimento (dd/mm/aaaa) e o código de receita da guia.', true); return; }
        selecao.e116 = { venc, cod_rec: cod };
      }
      overlay(true, 'Ajustando o crédito de ICMS ao destacado nos XMLs…');
      const res = await window.fiscocont.admin.icmsXmlAplicar({ spedPath: corrSpedPath, usarCorrigido: corrFeito, xmls: XMLS.path, selecao });
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      corrFeito = true;
      const r = res.resumo || {}, ea = r.e110_antes, ed = r.e110_depois, out = $('#ixRes');
      out.innerHTML = `
        <div class="dif-done sn-done">
          <div class="dif-k">Corrigido: arquivo novo gerado (o original não foi alterado)</div>
          <div class="dif-kpis">
            <div class="k-ok"><span>Notas corrigidas</span><b data-n="${r.notas || 0}">0</b><small>${r.c170 || 0} item(ns) (C170) ajustado(s)</small></div>
            <div class="k-err"><span>Crédito retirado</span><b data-n="${r.credito_retirado || 0}" data-fmt="brl">R$ 0,00</b><small>campo 06 do E110</small></div>
            ${ea && ed ? `<div><span>ICMS a recolher</span><b data-n="${ed.recolher}" data-fmt="brl">R$ 0,00</b><small>antes R$ ${fm(ea.recolher)}</small></div>
            <div><span>Saldo credor a transportar</span><b data-n="${ed.sld_transp}" data-fmt="brl">R$ 0,00</b><small>antes R$ ${fm(ea.sld_transp)}</small></div>` : ''}
          </div>
          ${r.e116 ? `<p class="dif-sub">${esc(r.e116)}</p>` : ''}
          ${(r.avisos || []).length ? `<div class="dif-av"><ul>${r.avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
          <div class="dif-acts">
            <button class="act inv-export" id="btnIxReconf">Conferir de novo</button>
            <button class="act inv-export sn-big" id="btnIxBaixar" style="background:#0ea472;color:#fff;border-color:transparent">Baixar SPED corrigido</button>
          </div>
        </div>`;
      animaNumeros(out);
      $('#btnIxBaixar').addEventListener('click', async () => {
        const r3 = await window.fiscocont.fiscal.baixarSpedCorrigido();
        if (r3.canceled) return;
        if (r3.error) { toast(r3.error, true); return; }
        toast('SPED corrigido salvo.');
        window.fiscocont.openPath(r3.path);
      });
      $('#btnIxReconf').addEventListener('click', ixAnalisar);
      out.scrollIntoView({ behavior: 'smooth', block: 'start' });
      toast('Crédito de ICMS ajustado ao XML — baixe o SPED corrigido.');
    }
    $('#btnCorrIcmsXml').addEventListener('click', () => ixAbrir());

    // ---- Valor do documento e base do ICMS × XML (entradas com crédito) ----
    const VX = { an: null, origem: null, sel: new Set() };
    function vxFechar() { $('#corrValXml').hidden = true; $('#corrSpedEmpty').hidden = false; }
    async function vxAbrir() {
      if (!corrSpedPath) return;
      ['#corrSpedEmpty', '#corrSpedFrame', '#corrSpedResumo', '#corrDifal', '#corrSimples', '#corrLote', '#corrIcmsXml', '#corrEstST'].forEach((s) => { const el = $(s); if (el) el.hidden = true; });
      $('#corrValXml').hidden = false;
      if (!XMLS.path) { vxVazio(); return; }
      await vxAnalisar();
    }
    function vxVazio() {
      const box = $('#corrValXml');
      box.innerHTML = `
        <div class="dif-head"><div>
          <div class="dif-k">Corretor do SPED · Admin · Valor e base × XML</div>
          <h3>Selecione os XMLs de entrada do período</h3>
          <div class="dif-sub">Cada nota de entrada é cruzada pela chave de acesso com o XML: valor do documento, base de cálculo e ICMS.</div>
        </div><button class="act inv-export" id="btnVxFechar">Fechar</button></div>
        <div class="sn-vazio"><p>Anexe a pasta ou os <b>.zip</b> com os XMLs das notas de entrada.</p>
          <button class="act inv-export sn-big" id="btnVxXmls">Selecionar XMLs</button></div>`;
      $('#btnVxFechar').addEventListener('click', vxFechar);
      $('#btnVxXmls').addEventListener('click', vxEscolherXmls);
    }
    async function vxEscolherXmls() {
      const pick = await window.fiscocont.fiscal.pickXmlsFolder();
      if (pick.canceled || !pick.path) return;
      XMLS.path = pick.path;
      await vxAnalisar();
    }
    async function vxAnalisar() {
      overlay(true, 'Conferindo valor do documento, base e ICMS do SPED com os XMLs…');
      const res = await window.fiscocont.admin.valorXmlAnalisar({ spedPath: corrSpedPath, usarCorrigido: corrFeito, xmls: XMLS.path });
      overlay(false);
      if (res.error) { toast(res.error, true); if (!VX.an) vxVazio(); return; }
      VX.an = res.res; VX.origem = res.origem;
      VX.sel = new Set((VX.an.docs || []).filter((d) => d.sugerido).map((d) => d.id));
      vxRender();
    }
    function vxPrev() {
      const an = VX.an, e = an.e110 || {};
      const docs = (an.docs || []).filter((d) => VX.sel.has(d.id));
      const red = docs.reduce((t, d) => t + (d.base === 'maior' ? d.reducao : 0), 0);
      const nDoc = docs.filter((d) => d.doc_dif).length, nBase = docs.filter((d) => d.base === 'maior').length;
      const cred = e.cred || 0, rec = e.recolher || 0, sld = e.sld_transp || 0;
      const credD = Math.max(0, cred - red);
      const recD = sld > 0 ? Math.max(0, red - sld) + rec : rec + red;
      const sldD = Math.max(0, sld - red);
      $('#vxPrev').innerHTML = `<table class="dif-mini"><thead><tr><th></th><th class="n">Antes</th><th class="n">Depois</th></tr></thead><tbody>
        <tr><td>Créditos (E110, campo 06)</td><td class="n">R$ ${fm(cred)}</td><td class="n ${red ? 'mud' : ''}">R$ ${fm(credD)}</td></tr>
        <tr><td>Saldo credor a transportar</td><td class="n">R$ ${fm(sld)}</td><td class="n">R$ ${fm(sldD)}</td></tr>
        <tr><td><b>ICMS a recolher</b></td><td class="n">R$ ${fm(rec)}</td><td class="n"><b>R$ ${fm(recD)}</b></td></tr></tbody></table>
        <div class="dif-sub" style="margin-top:6px">Marcado: <b>${nDoc}</b> nota(s) com valor do documento corrigido (não muda a apuração) · <b>${nBase}</b> com base/ICMS corrigidos${red ? ` · crédito retirado <b>R$ ${fm(red)}</b>` : ''}</div>`;
      $('#btnVxAplicar').disabled = !VX.sel.size;
      $('#vxE116').hidden = !(red > 0 && recD > 0 && !(an.e116 || []).some((g) => g.cod === '000'));
    }
    const VX_BASE = { maior: ['Base maior que o XML', 'b-err'], maior_sem_item: ['Base acima, fora dos itens', 'b-warn'], menor: ['Base menor que o XML', 'b-mute'] };
    function vxLinha(d) {
      const b = VX_BASE[d.base];
      const tags = [d.doc_dif ? '<span class="dif-b b-warn">Valor do documento diferente</span>' : '', b ? `<span class="dif-b ${b[1]}">${b[0]}</span>` : ''].filter(Boolean).join(' ');
      const vv = (a, x, dif) => dif ? `<span class="v-old">R$ ${fm(a)}</span><span class="v-new">R$ ${fm(x)}</span>` : `R$ ${fm(a)}<small>igual</small>`;
      const acao = [d.doc_dif ? 'Corrige o C100 pelo XML e refaz o VL_OPR do C190' : '', d.base === 'maior' ? 'Corrige base e ICMS pelo XML e refaz o E110' : '',
        d.base === 'menor' ? 'Só informa: crédito que pode ser recuperado' : '', d.base === 'maior_sem_item' ? 'Corrigir à mão' : ''].filter(Boolean).join(' · ');
      const itens = (d.itens || []).map((i) => `<tr><td>${esc(i.num)}</td><td>${esc(i.descr)}<small>XML: ${esc(i.xprod)}</small></td><td>${esc(i.cfop)}</td>
        <td>${esc(i.cst_sped)} → ${esc(i.cst_xml)}</td><td class="n">R$ ${fm(i.bc_sped)} → R$ ${fm(i.bc_xml)}</td><td class="n">${fa(i.aliq_sped)} → ${fa(i.aliq_xml)}</td>
        <td class="n">R$ ${fm(i.icms_sped)} → R$ ${fm(i.icms_xml)}</td></tr>`).join('');
      return `<tr class="${d.sugerido ? '' : 'dif-off'}">
        <td><label class="dif-ck"><input type="checkbox" class="vx-ck" data-id="${d.id}" ${VX.sel.has(d.id) ? 'checked' : ''} ${d.sugerido ? '' : 'disabled'}> <b>${esc(d.num)}</b></label><small>${dt(d.data)}</small></td>
        <td>${esc(d.fornecedor)}${d.simples ? ' <span class="dif-b b-warn">Simples</span>' : ''}<small>${esc(d.cnpj)} · ${esc(d.uf || '')}</small></td>
        <td class="n">${vv(d.vl_doc_sped, d.vl_doc_xml, d.doc_dif)}</td>
        <td class="n">${vv(d.bc_sped, d.bc_xml, Math.abs(d.bc_sped - d.bc_xml) > 0.01)}</td>
        <td class="n">${vv(d.icms_sped, d.icms_xml, Math.abs(d.icms_sped - d.icms_xml) > 0.01)}</td>
        <td style="white-space:normal;max-width:300px">${tags}${(d.obs || []).map((o) => `<small style="white-space:normal">${esc(o)}</small>`).join('')}</td>
        <td style="white-space:normal;max-width:220px">${acao}</td></tr>
        ${itens ? `<tr class="ix-det"><td colspan="7"><details class="mono-ex" style="margin:0"><summary>ver os ${d.itens.length} item(ns) com diferença de base/ICMS</summary>
          <table class="dif-tab" style="margin-top:6px"><thead><tr><th>Item</th><th>Produto</th><th>CFOP</th><th>CST SPED → XML</th><th class="n">Base</th><th class="n">Alíquota</th><th class="n">ICMS</th></tr></thead><tbody>${itens}</tbody></table></details></td></tr>` : ''}`;
    }
    function vxRender() {
      const an = VX.an, emp = an.empresa || {}, rs = an.resumo || {}, box = $('#corrValXml'), docs = an.docs || [], fo = an.fora || {};
      const e116 = (an.e116 || []).find((g) => g.cod === '000') || (an.e116 || [])[0] || {};
      const chips = [fo.uso_ativo && fo.uso_ativo.length ? `Uso e consumo / ativo (crédito pelo CIAP) · ${fo.uso_ativo.length}` : '',
        fo.canceladas ? `Canceladas / denegadas · ${fo.canceladas}` : '', (fo.sem_xml || []).length ? `Sem XML · ${fo.sem_xml.length}` : ''].filter(Boolean);
      box.innerHTML = `
        <div class="dif-head"><div>
          <div class="dif-k">Corretor do SPED · Admin · Valor do documento e base × XML · entradas com crédito</div>
          <h3>${esc(emp.nome || '')}</h3>
          <div class="dif-sub">CNPJ ${esc(emp.cnpj || '')} · período ${dt(emp.dt_ini)} a ${dt(emp.dt_fin)} · arquivo <b>${VX.origem === 'corrigido' ? 'já corrigido nesta sessão' : 'original'}</b> · ${rs.xml_lidos ?? 0} XMLs lidos</div>
        </div>
        <div class="sn-hbtn"><button class="act inv-export" id="btnVxXmls">Trocar XMLs</button><button class="act inv-export" id="btnVxFechar">Fechar</button></div></div>
        <div class="dif-kpis">
          <div class="k-ok"><span>Notas que batem</span><b data-n="${rs.batem || 0}">0</b><small>de ${rs.notas_conferidas || 0} conferida(s)</small></div>
          <div class="k-err"><span>Base maior que o XML</span><b data-n="${rs.base_maior || 0}">0</b><small>crédito a mais: R$ ${fm(rs.credito_a_retirar)}${rs.base_maior_sem_item ? ` · ${rs.base_maior_sem_item} fora dos itens` : ''}</small></div>
          <div class="k-warn"><span>Valor do documento diferente</span><b data-n="${rs.doc_dif || 0}">0</b><small>diferença total R$ ${fm(rs.doc_dif_total)}</small></div>
          <div><span>Base menor que o XML</span><b data-n="${rs.base_menor || 0}">0</b><small>só informativo · R$ ${fm(rs.credito_nao_tomado)}</small></div>
          <div><span>Fora da conferência</span><b data-n="${(rs.fora_uso_ativo || 0) + (rs.fora_canceladas || 0) + (rs.sem_xml || 0)}">0</b><small>uso/consumo, ativo, canceladas, sem XML</small></div>
        </div>
        ${docs.length ? `
        <div class="mono-card"><div class="dif-k">Notas com diferença — marque o que corrigir</div>
          <div class="dif-tw" style="margin-top:8px;max-height:620px"><table class="dif-tab"><thead><tr><th>Nota</th><th>Fornecedor</th><th class="n">Valor do documento<br>SPED → XML</th><th class="n">Base ICMS<br>SPED → XML</th><th class="n">ICMS<br>SPED → XML</th><th>Resultado</th><th>O que o sistema faz</th></tr></thead>
          <tbody>${docs.map(vxLinha).join('')}</tbody></table></div></div>
        <div class="mono-grid">
          <div class="mono-card"><div class="dif-k">Apuração (E110) antes × depois</div><div id="vxPrev"></div></div>
          <div class="mono-card">
            <div class="dif-e116" id="vxE116" hidden style="margin-top:10px"><div class="dif-sub"><b>A empresa passa a ter ICMS a recolher e o SPED não tem guia (E116):</b></div>
              <label>Vencimento <input id="vxVenc" placeholder="dd/mm/aaaa" value="${e116.venc ? dt(e116.venc) : ''}"></label>
              <label>Código de receita <input id="vxCodRec" placeholder="ex.: 1210" value="${esc(e116.cod_rec || '')}"></label></div>
            <div class="dif-sub" style="margin-top:10px"><b>O que o arquivo novo muda:</b> valor do documento diferente — o C100 recebe os totais do XML (valor do documento, desconto, mercadorias, frete, seguro e outras despesas)
              e o VL_OPR do C190 é refeito para somar o valor da nota; base e ICMS não mudam. Base maior que o XML — base, alíquota e ICMS do item (C170) vão para o que o XML destaca, o C190 e o C100 são refeitos e o campo 06 do E110 diminui.
              Base menor fica como está. Uso e consumo e ativo não são mexidos. O original nunca é alterado.</div>
            <div class="dif-sub">Base legal: o C100 repete os totais da nota e o crédito é o imposto destacado na nota da operação anterior (Guia Prático da EFD ICMS/IPI, registros C100 e C190; LC 87/96, arts. 19, 20 e 23).</div>
            <div class="dif-acts"><button class="act inv-export" id="btnVxAplicar" style="background:#e23d4c;color:#fff;border-color:transparent">Aplicar no SPED (gera arquivo novo)</button></div>
          </div>
        </div>
        <div id="vxRes"></div>` : `<div class="dif-av ok">Valor do documento, base e ICMS do SPED batem com os XMLs em todas as ${rs.notas_conferidas || 0} nota(s) conferidas.</div>`}
        ${chips.length ? `<div class="mono-card"><div class="dif-k">Fora da conferência (não entram, porque não dão crédito ou têm regra própria)</div>
          <div class="dif-sub" style="margin-top:6px">${chips.map((c) => `<span class="pill p-x" style="margin:0 6px 6px 0;display:inline-block">${esc(c)}</span>`).join('')}</div>
          ${(fo.sem_xml || []).length ? `<details class="mono-ex" style="margin:6px 0 0"><summary>Entradas sem XML — ${fo.sem_xml.length} nota(s)</summary>
          <div class="dif-tw" style="max-height:320px"><table class="dif-tab"><thead><tr><th>Nota</th><th>Fornecedor</th><th>Chave de acesso</th><th class="n">Valor no SPED</th></tr></thead>
          <tbody>${fo.sem_xml.map((z) => `<tr><td><b>${esc(z.num)}</b><small>${dt(z.data)}</small></td><td>${esc(z.fornecedor)}<small>${esc(z.cnpj)}</small></td><td style="font-family:monospace;font-size:11.5px">${esc(z.chave)}</td><td class="n">R$ ${fm(z.vl_doc)}</td></tr>`).join('')}</tbody></table></div></details>` : ''}</div>` : ''}`;
      animaNumeros(box);
      $('#btnVxFechar').addEventListener('click', vxFechar);
      $('#btnVxXmls').addEventListener('click', vxEscolherXmls);
      if (!docs.length) return;
      box.querySelectorAll('.vx-ck').forEach((c) => c.addEventListener('change', () => { const id = Number(c.dataset.id); c.checked ? VX.sel.add(id) : VX.sel.delete(id); vxPrev(); }));
      vxPrev();
      $('#btnVxAplicar').addEventListener('click', vxAplicar);
    }
    async function vxAplicar() {
      const selecao = { docs: [...VX.sel] };
      if (!$('#vxE116').hidden) {
        const venc = ($('#vxVenc').value || '').replace(/\D/g, ''), cod = ($('#vxCodRec').value || '').trim();
        if (venc.length !== 8 || !cod) { toast('Informe o vencimento (dd/mm/aaaa) e o código de receita da guia.', true); return; }
        selecao.e116 = { venc, cod_rec: cod };
      }
      overlay(true, 'Corrigindo valor do documento e base pelo XML…');
      const res = await window.fiscocont.admin.valorXmlAplicar({ spedPath: corrSpedPath, usarCorrigido: corrFeito, xmls: XMLS.path, selecao });
      overlay(false);
      if (res.error) { toast(res.error, true); return; }
      corrFeito = true;
      const r = res.resumo || {}, ea = r.e110_antes, ed = r.e110_depois, out = $('#vxRes');
      out.innerHTML = `
        <div class="dif-done sn-done">
          <div class="dif-k">Corrigido: arquivo novo gerado (o original não foi alterado)</div>
          <div class="dif-kpis">
            <div class="k-ok"><span>Notas corrigidas</span><b data-n="${r.notas || 0}">0</b><small>${r.notas_doc || 0} no valor do documento · ${r.notas_base || 0} na base (${r.c170 || 0} item(ns))</small></div>
            <div class="k-err"><span>Crédito retirado</span><b data-n="${r.credito_retirado || 0}" data-fmt="brl">R$ 0,00</b><small>campo 06 do E110</small></div>
            ${ea && ed ? `<div><span>ICMS a recolher</span><b data-n="${ed.recolher}" data-fmt="brl">R$ 0,00</b><small>antes R$ ${fm(ea.recolher)}</small></div>` : ''}
          </div>
          ${(r.detalhe || []).length ? `<div class="dif-sub"><ul>${r.detalhe.slice(0, 40).map((x) => `<li><b>NF ${esc(x.num)}</b> · ${esc(x.fornecedor)}: ${esc((x.feito || []).join('; '))}</li>`).join('')}</ul></div>` : ''}
          ${r.e116 ? `<p class="dif-sub">${esc(r.e116)}</p>` : ''}
          ${(r.avisos || []).length ? `<div class="dif-av"><ul>${r.avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
          <div class="dif-acts">
            <button class="act inv-export" id="btnVxReconf">Conferir de novo</button>
            <button class="act inv-export sn-big" id="btnVxBaixar" style="background:#0ea472;color:#fff;border-color:transparent">Baixar SPED corrigido</button>
          </div>
        </div>`;
      animaNumeros(out);
      $('#btnVxBaixar').addEventListener('click', async () => {
        const r3 = await window.fiscocont.fiscal.baixarSpedCorrigido();
        if (r3.canceled) return;
        if (r3.error) { toast(r3.error, true); return; }
        toast('SPED corrigido salvo.');
        window.fiscocont.openPath(r3.path);
      });
      $('#btnVxReconf').addEventListener('click', vxAnalisar);
      out.scrollIntoView({ behavior: 'smooth', block: 'start' });
      toast('Valor do documento e base ajustados ao XML — baixe o SPED corrigido.');
    }
    $('#btnCorrValXml').addEventListener('click', () => vxAbrir());

    // ---- Estoque de mercadoria que saiu da ST: crédito + inventário (RICMS/RO, Anexo VI, arts. 46 a 48) ----
    const EST = { planilha: null, res: null, origem: null, params: { dt_inv: '', unid: '', upf: '', st_pago: {} } };
    const ddmm = (v) => (v && v.length === 8 ? `${v.slice(0, 2)}/${v.slice(2, 4)}/${v.slice(4)}` : '');
    function estFechar() { $('#corrEstST').hidden = true; $('#corrSpedEmpty').hidden = false; }
    function estAbrir() {
      if (!corrSpedPath) return;
      ['#corrSpedEmpty', '#corrSpedFrame', '#corrSpedResumo', '#corrDifal', '#corrSimples', '#corrLote', '#corrIcmsXml', '#corrValXml'].forEach((x) => { const el = $(x); if (el) el.hidden = true; });
      $('#corrEstST').hidden = false;
      if (EST.res) estRender(); else estEntrada();
    }
    function estEntrada() {
      const box = $('#corrEstST');
      box.innerHTML = `
        <div class="dif-head"><div>
          <div class="dif-k">Corretor do SPED · Admin · Estoque de mercadoria que saiu da substituição tributária</div>
          <h3>Crédito do estoque e inventário da mudança de tributação</h3>
          <div class="dif-sub">RICMS/RO, Anexo VI, arts. 46 a 48: para cada item, base da ST da nota de entrada × alíquota interna, lançado no E111 (RO020033), com o inventário no Bloco H (motivo 02).</div>
        </div><button class="act inv-export" id="btnEstFechar">Fechar</button></div>
        <div class="sn-vazio">
          <p><b>1.</b> Planilha do estoque na data da mudança (Código, Descrição, Quantidade, Valor Unitário): ${EST.planilha ? `<b>${esc(EST.planilha.split(/[\\/]/).pop())}</b>` : 'não selecionada'}</p>
          <button class="act inv-export sn-big" id="btnEstPlan">${EST.planilha ? 'Trocar planilha' : 'Selecionar planilha'}</button>
          <p style="margin-top:14px"><b>2.</b> XMLs das notas de entrada desses itens (a última compra de cada um; uma nota por fornecedor já serve quando o preço da planilha é o da nota): ${XMLS.path ? '<b>anexados</b>' : 'não anexados'}</p>
          <button class="act inv-export sn-big" id="btnEstXml">${XMLS.path ? 'Trocar XMLs' : 'Selecionar XMLs'}</button>
          <div class="dif-acts" style="margin-top:16px"><button class="act inv-export" id="btnEstCalc" style="background:var(--accent);color:#fff;border-color:transparent" ${EST.planilha && XMLS.path ? '' : 'disabled'}>Calcular o crédito</button></div>
        </div>`;
      $('#btnEstFechar').addEventListener('click', estFechar);
      $('#btnEstPlan').addEventListener('click', async () => { const r = await window.fiscocont.admin.estoqueStPlanilha(); if (r.path) { EST.planilha = r.path; estEntrada(); } });
      $('#btnEstXml').addEventListener('click', async () => { const r = await window.fiscocont.fiscal.pickXmlsFolder(); if (r.path) { XMLS.path = r.path; estEntrada(); } });
      $('#btnEstCalc').addEventListener('click', estCalcular);
    }
    async function estCalcular() {
      overlay(true, 'Ligando a planilha às notas de entrada e calculando a base da ST de cada item…');
      const r = await window.fiscocont.admin.estoqueStCalcular({ spedPath: corrSpedPath, usarCorrigido: corrFeito, planilha: EST.planilha, xmls: XMLS.path, params: estParams() });
      overlay(false);
      if (r.error) { toast(r.error, true); return; }
      EST.res = r.res; EST.origem = r.origem;
      if (!EST.params.dt_inv) {
        const di = (EST.res.empresa || {}).dt_ini || '';
        if (di.length === 8) { const d = new Date(+di.slice(4), +di.slice(2, 4) - 1, +di.slice(0, 2) - 1); EST.params.dt_inv = String(d.getDate()).padStart(2, '0') + String(d.getMonth() + 1).padStart(2, '0') + d.getFullYear(); }
      }
      if (!EST.params.unid) { const u = (EST.res.unidades || []).find((x) => /^UNIDADE$/i.test(x.descr.trim())) || (EST.res.unidades || [])[0]; EST.params.unid = u ? u.cod : ''; }
      estRender();
    }
    function estParams() { return { dt_inv: EST.params.dt_inv, unid: EST.params.unid, upf: EST.params.upf ? Number(String(EST.params.upf).replace(',', '.')) : undefined, st_pago: EST.params.st_pago }; }
    function estRender() {
      const r = EST.res, emp = r.empresa || {}, rs = r.resumo || {}, e = r.e110 || {}, box = $('#corrEstST');
      const ok = (r.itens || []).filter((i) => i.status === 'ok');
      const credito = r.credito_apropriado || 0;
      const forn = [...new Set(ok.map((i) => `${i.fornecedor} (${i.uf}) · NF ${i.nota}`))];
      const linha = (i) => i.status !== 'ok'
        ? `<tr class="dif-off"><td><b>${esc(i.cod)}</b></td><td>${esc(i.descr)}</td><td class="n">${fm(i.qtd).replace(',00', '')}</td><td class="n">R$ ${fm(i.valor)}</td><td colspan="5"><span class="dif-b b-warn">sem nota</span><small>${esc(i.obs || '')}</small></td></tr>`
        : `<tr><td><b>${esc(i.cod)}</b></td><td>${esc(i.descr)}<small>NF ${esc(i.nota)} · ${esc(i.item_xml)} (pacote de ${i.pacote})</small></td>
          <td class="n">${fm(i.qtd).replace(',00', '')}</td><td class="n">R$ ${fm(i.valor)}<small>R$ ${fp(i.vunit)} / un.</small></td>
          <td class="n">${fa(i.aliq_inter)}<small>IPI R$ ${fp(i.ipi_unit)} / un.</small></td><td class="n">${fa(i.mva_aj)}</td>
          <td class="n">R$ ${fp(i.bc_unit)}<small>por unidade</small></td><td class="n">${fa(i.aliq_interna)}</td><td class="n"><b>R$ ${fm(i.credito)}</b><small>R$ ${fp(i.icms_unit)} / un.</small></td></tr>`;
      const uni = (r.unidades || []).map((u) => `<option value="${esc(u.cod)}" ${u.cod === EST.params.unid ? 'selected' : ''}>${esc(u.cod)} · ${esc(u.descr)}</option>`).join('');
      box.innerHTML = `
        <div class="dif-head"><div>
          <div class="dif-k">Corretor do SPED · Admin · Estoque que saiu da substituição tributária</div>
          <h3>${esc(emp.nome || '')}</h3>
          <div class="dif-sub">CNPJ ${esc(emp.cnpj || '')} · período ${dt(emp.dt_ini)} a ${dt(emp.dt_fin)} · arquivo <b>${EST.origem === 'corrigido' ? 'já corrigido nesta sessão' : 'original'}</b> · ${r.xml_itens || 0} itens nos XMLs</div>
        </div><div class="sn-hbtn"><button class="act inv-export" id="btnEstTrocar">Trocar planilha/XMLs</button><button class="act inv-export" id="btnEstFechar">Fechar</button></div></div>
        <div class="dif-kpis">
          <div><span>Itens no estoque</span><b data-n="${rs.itens || 0}">0</b><small>${fm(rs.qtd).replace(',00', '')} unidades · R$ ${fm(rs.valor_estoque)}</small></div>
          <div class="k-ok"><span>Itens calculados pela nota</span><b data-n="${rs.calculados || 0}">0</b><small>${rs.sem_xml ? `${rs.sem_xml} sem nota de entrada` : 'todos os itens'}</small></div>
          <div class="k-ok"><span>Crédito do estoque</span><b data-n="${r.credito_total || 0}" data-fmt="brl">R$ 0,00</b><small>E111 RO020033 · campo 08 do E110</small></div>
          <div><span>ICMS a recolher</span><b data-n="${Math.max(0, (e.recolher || 0) - credito)}" data-fmt="brl">R$ 0,00</b><small>antes R$ ${fm(e.recolher)}</small></div>
        </div>
        ${(r.avisos || []).map((a) => `<div class="dif-av">${esc(a)}</div>`).join('')}
        <div class="mono-card"><div class="dif-k">ST de cada nota — conferência opcional</div>
          <div class="dif-sub" style="margin:4px 0 8px">O crédito sai pela regra cheia (MVA ajustada e alíquota interna, sem benefício). Só preencha a "ST paga" se a empresa tiver benefício ou regime especial na ST: aí o crédito dos itens da nota acompanha a proporção do que foi pago (Anexo VI, art. 46, § 2º). Sem benefício, deixe em branco e aplique.</div>
          <div class="dif-tw"><table class="dif-tab"><thead><tr><th>Nota de entrada</th><th class="n">Base da ST da nota</th><th class="n">ICMS total (37%)</th><th class="n">ICMS da compra</th><th class="n">ST esperada</th><th class="n">ST paga (DARE)</th><th>Situação</th><th class="n">Crédito dos itens</th></tr></thead>
          <tbody>${(r.notas || []).map((n) => `<tr><td><b>NF ${esc(n.nota)}</b><small>${esc(n.fornecedor)} (${esc(n.uf)}) · ${esc(n.data)} · ${n.itens_estoque} de ${n.itens_nota} itens no estoque</small></td>
            <td class="n">R$ ${fm(n.bc_st)}</td><td class="n">R$ ${fm(n.icms_total)}</td><td class="n">R$ ${fm(n.icms_proprio)}</td><td class="n"><b>R$ ${fm(n.st_esperado)}</b></td>
            <td class="n"><input class="est-pago" data-nota="${esc(n.nota)}" value="${n.st_pago != null ? fm(n.st_pago) : ''}" placeholder="valor pago" style="width:120px;text-align:right;padding:6px 8px;border:1px solid var(--line);border-radius:8px"></td>
            <td>${n.situacao === 'pendente' ? '<span class="dif-b b-ok">regra cheia</span>' : n.situacao === 'confere' ? '<span class="dif-b b-ok">confere</span>' : `<span class="dif-b b-err">diferente</span><small>crédito ajustado para ${fa(n.fator * 100)}</small>`}</td>
            <td class="n"><b>R$ ${fm(n.credito)}</b></td></tr>`).join('')}</tbody></table></div></div>
        <div class="mono-card"><div class="dif-k">Crédito item por item — base da ST (preço da nota + IPI, × MVA ajustada) × alíquota interna</div>
          <div class="dif-sub" style="margin:4px 0 8px">Notas usadas: ${forn.map(esc).join(' · ') || '—'}</div>
          <div class="dif-tw" style="max-height:560px"><table class="dif-tab"><thead><tr><th>Código</th><th>Produto</th><th class="n">Qtd.</th><th class="n">Valor do estoque</th><th class="n">Alíq. interestadual</th><th class="n">MVA ajustada</th><th class="n">Base da ST</th><th class="n">Alíq. interna</th><th class="n">Crédito</th></tr></thead>
          <tbody>${(r.itens || []).map(linha).join('')}</tbody>
          <tfoot><tr><td colspan="3"><b>Total</b></td><td class="n"><b>R$ ${fm(rs.valor_estoque)}</b></td><td colspan="4"></td><td class="n"><b>R$ ${fm(r.credito_total)}</b></td></tr></tfoot></table></div></div>
        <div class="mono-grid">
          <div class="mono-card"><div class="dif-k">O que vai para o SPED</div>
            <div class="usr-form" style="grid-template-columns:1fr 1.4fr 1fr">
              <label>Data do inventário<input id="estDt" value="${ddmm(EST.params.dt_inv)}" placeholder="dd/mm/aaaa"></label>
              <label>Unidade (0190)<select id="estUn">${uni}</select></label>
              <label>UPF/RO do mês (opcional)<input id="estUpf" value="${esc(EST.params.upf || '')}" placeholder="confere o limite"></label>
            </div>
            <div class="dif-sub" style="margin-top:10px">• Inventário <b>H005</b> com motivo <b>02</b> (mudança na forma de tributação) na data acima, <b>H010</b> de cada item e <b>H020</b> com CST 000, base e ICMS por unidade (art. 47).<br>
              • Cadastro <b>0200</b> dos itens que ainda não estão no SPED.<br>
              • Ajuste <b>E111 RO020033</b> "Crédito mudança de tributação - Art. 48 - anexo VI do RICMS" de R$ ${fm(credito)}; o E110 e a guia E116 são refeitos e o Bloco 9 recontado. O original nunca é alterado.<br>
              • Limite: 5.000 UPF/RO por mês (art. 48, parágrafo único). Informe a UPF para o sistema conferir.</div>
            <div class="dif-acts"><button class="act inv-export" id="btnEstAplicar" style="background:#e23d4c;color:#fff;border-color:transparent" ${ok.length ? '' : 'disabled'}>Aplicar no SPED (gera arquivo novo)</button></div>
          </div>
          <div class="mono-card"><div class="dif-k">Base legal</div>
            <div class="dif-sub">RICMS/RO (Dec. 22.721/2018), Anexo VI: art. 14, I, "b", 3 (base da ST: preço do remetente + frete, seguro, impostos e encargos, + MVA); arts. 45 a 48 (estoque de mercadoria excluída da ST, redação do Dec. 29.184/2024).
              Vinhos (CEST 02.024.00): MVA original 53,63%, ajustada 126,78% para 7% (Parte 2, Tabela III, item 24.0), revogado pelo Dec. 31.963/2026 a partir de 1º/09/2026. Alíquota interna de bebidas alcoólicas, exceto cerveja: 37% (Lei 688/96, art. 27, I, "h").</div></div>
        </div>
        <div id="estRes"></div>`;
      animaNumeros(box);
      $('#btnEstFechar').addEventListener('click', estFechar);
      $('#btnEstTrocar').addEventListener('click', () => { EST.res = null; estEntrada(); });
      $('#estDt').addEventListener('change', (ev) => { EST.params.dt_inv = ev.target.value.replace(/\D/g, ''); });
      $('#estUn').addEventListener('change', (ev) => { EST.params.unid = ev.target.value; });
      $('#estUpf').addEventListener('change', async (ev) => { EST.params.upf = ev.target.value; await estCalcular(); });
      box.querySelectorAll('.est-pago').forEach((inp) => inp.addEventListener('change', async () => {
        const v = inp.value.trim();
        if (v) EST.params.st_pago[inp.dataset.nota] = v.replace(/\./g, '').replace(',', '.'); else delete EST.params.st_pago[inp.dataset.nota];
        await estCalcular();
      }));
      $('#btnEstAplicar').addEventListener('click', estAplicar);
    }
    async function estAplicar() {
      if ((EST.params.dt_inv || '').length !== 8) { toast('Informe a data do inventário (dd/mm/aaaa).', true); return; }
      overlay(true, 'Incluindo o inventário e o crédito no SPED…');
      const r = await window.fiscocont.admin.estoqueStAplicar({ spedPath: corrSpedPath, usarCorrigido: corrFeito, planilha: EST.planilha, xmls: XMLS.path, params: estParams() });
      overlay(false);
      if (r.error) { toast(r.error, true); return; }
      corrFeito = true;
      const a = r.res.aplicado || {}, ea = a.e110_antes || {}, ed = a.e110_depois || {};
      const out = $('#estRes');
      out.innerHTML = `<div class="dif-done sn-done"><div class="dif-k">Incluído: arquivo novo gerado (o original não foi alterado)</div>
        <div class="dif-kpis">
          <div class="k-ok"><span>Itens no inventário</span><b data-n="${a.itens || 0}">0</b><small>H005 motivo 02 · ${(a.r0200_criados || []).length} cadastro(s) 0200 criados</small></div>
          <div class="k-ok"><span>Crédito lançado</span><b data-n="${a.credito || 0}" data-fmt="brl">R$ 0,00</b><small>E111 RO020033</small></div>
          <div><span>ICMS a recolher</span><b data-n="${ed.recolher || 0}" data-fmt="brl">R$ 0,00</b><small>antes R$ ${fm(ea.recolher)}</small></div>
        </div>
        ${a.e116 ? `<p class="dif-sub">${esc(a.e116)}</p>` : ''}
        ${(a.avisos || []).length ? `<div class="dif-av"><ul>${a.avisos.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
        <div class="dif-acts"><button class="act inv-export sn-big" id="btnEstBaixar" style="background:#0ea472;color:#fff;border-color:transparent">Baixar SPED corrigido</button></div></div>`;
      animaNumeros(out);
      $('#btnEstBaixar').addEventListener('click', async () => {
        const r3 = await window.fiscocont.fiscal.baixarSpedCorrigido();
        if (r3.canceled) return;
        if (r3.error) { toast(r3.error, true); return; }
        toast('SPED corrigido salvo.'); window.fiscocont.openPath(r3.path);
      });
      out.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    $('#btnCorrEstST').addEventListener('click', () => estAbrir());

    const SN = { an: null, origem: null, filtro: 'pend' };
    const SN_ST = {
      incluir: ['Crédito a incluir', 'b-err', '#2a78d6'],
      lugar_errado: ['Crédito no lugar errado', 'b-err', '#eb6834'],
      sem_direito: ['Sem direito a crédito', 'b-err', '#e87ba4'],
      divergente: ['C197 divergente', 'b-warn', '#eda100'],
      sem_aliq: ['Falta a alíquota', 'b-warn', '#4a3aa7'],
      sem_xml: ['Sem XML', 'b-mute', '#8a93a8'],
      uso_consumo: ['Uso e consumo · sem crédito', 'b-mute', '#8a93a8'],
      ok: ['Correto', 'b-ok', '#1baf7a'],
    };
    const fp = (v) => (Number(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    const spf = (v) => (Number(v) || 0).toFixed(2).replace('.', ',');   // formato do arquivo SPED (sem milhar)
    const num = (t) => Number(String(t ?? '').replace(/\./g, '').replace(',', '.')) || 0;

    async function snAbrir() {
      if (!corrSpedPath) return;
      $('#corrSpedEmpty').hidden = true; $('#corrSpedFrame').hidden = true; $('#corrSpedResumo').hidden = true;
      $('#corrDifal').hidden = true;
      $('#corrIcmsXml').hidden = true; $('#corrValXml').hidden = true; $('#corrEstST').hidden = true;
      const box = $('#corrSimples');
      box.hidden = false;
      if (!XMLS.path) { snVazio(); return; }
      await snAnalisar();
    }

    function snVazio() {
      const box = $('#corrSimples');
      box.innerHTML = `
        <div class="dif-head"><div>
          <div class="dif-k">Corretor do SPED · Admin · crédito de fornecedor do Simples Nacional</div>
          <h3>Selecione os XMLs de entrada do período</h3>
          <div class="dif-sub">O percentual e o valor do crédito vêm do XML de cada nota (pCredSN e vCredICMSSN).</div>
        </div><button class="act inv-export" id="btnSnFechar">Fechar</button></div>
        <div class="sn-vazio">
          <svg viewBox="0 0 24 24"><path d="M4 4h10l6 6v10H4z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M14 4v6h6M8 14h8M8 17h5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
          <p>Anexe um ou mais <b>.zip</b> com os XMLs das notas de entrada. O sistema cruza cada nota pela chave de acesso com o SPED.</p>
          <button class="act inv-export sn-big" id="btnSnXmls">Selecionar XMLs (.zip)</button>
        </div>`;
      $('#btnSnFechar').addEventListener('click', snFechar);
      $('#btnSnXmls').addEventListener('click', snEscolherXmls);
    }
    function snFechar() { $('#corrSimples').hidden = true; $('#corrSpedEmpty').hidden = false; }

    async function snEscolherXmls() {
      const pick = await window.fiscocont.fiscal.pickXmlsFolder();
      if (pick.canceled || !pick.path) return;
      XMLS.path = pick.path;
      await snAnalisar();
    }

    async function snAnalisar() {
      overlay(true, 'Lendo os XMLs e conferindo o crédito do Simples Nacional…');
      const res = await window.fiscocont.admin.simplesAnalisar({ spedPath: corrSpedPath, usarCorrigido: corrFeito, xmls: XMLS.path });
      overlay(false);
      if (res.error) { toast(res.error, true); if (!SN.an) snVazio(); return; }
      SN.an = res.res; SN.origem = res.origem;
      snRender();
    }

    function snCredito(d, aliq) {
      if (d.credito > 0 && Math.abs(aliq - d.aliq) < 0.0001) return d.credito;
      return r2(d.base * aliq / 100);
    }
    const snEditavel = (d) => ['incluir', 'lugar_errado', 'divergente', 'sem_aliq'].includes(d.status);

    function snRender() {
      const an = SN.an, emp = an.empresa || {}, rs = an.resumo || {}, box = $('#corrSimples');
      const docs = an.docs || [];
      const nArq = String(XMLS.path || '').split(/[;:](?![\\/])/).filter(Boolean).length;
      const pend = docs.filter((d) => d.status !== 'ok');
      const grupos = Object.keys(SN_ST).map((k) => {
        const ds = docs.filter((d) => d.status === k);
        const v = ds.reduce((t, d) => t + (k === 'lugar_errado' || k === 'sem_direito' ? d.c190_icms : k === 'divergente' ? Math.abs(d.credito - d.c197) : k === 'sem_xml' ? d.c197 : d.credito), 0);
        return { k, n: ds.length, v: r2(v) };
      }).filter((g) => g.n);
      const maxN = Math.max(1, ...grupos.map((g) => g.n));
      box.innerHTML = `
        <div class="dif-head"><div>
          <div class="dif-k">Corretor do SPED · Admin · crédito de fornecedor do Simples Nacional</div>
          <h3>${esc(emp.nome || '')}</h3>
          <div class="dif-sub">CNPJ ${esc(emp.cnpj || '')} · período ${dt(emp.dt_ini)} a ${dt(emp.dt_fin)} · arquivo <b>${SN.origem === 'corrigido' ? 'já corrigido nesta sessão' : 'original'}</b> ·
            ${rs.xml_lidos ?? 0} XMLs lidos (${nArq} .zip)</div>
        </div>
        <div class="sn-hbtn"><button class="act inv-export" id="btnSnXmls">Trocar XMLs</button><button class="act inv-export" id="btnSnFechar">Fechar</button></div></div>
        <div class="dif-lei"><b>Como RO manda escriturar:</b> a nota do fornecedor do Simples entra <b>sem ICMS</b> no C100/C170/C190. O crédito permitido vai num <b>C197 por nota</b>
          com o código <b>RO00000001</b>: base = valor da operação, alíquota = percentual do Simples informado na nota, ICMS = crédito.
          A soma desses C197 entra no <b>campo 07 do E110</b>. Fontes: SEFIN/RO, IN 017/2016 (Tabela 5.3 e manual da EFD, item 19); LC 123/2006, art. 23, §§ 1º a 5º.</div>
        ${(an.avisos || []).length ? `<div class="dif-av"><ul>${an.avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
        <div class="dif-kpis sn-kpis">
          <div><span>Notas do Simples</span><b data-n="${rs.notas_simples || 0}">0</b><small>${rs.entradas ?? 0} entradas no SPED · ${rs.entradas_sem_xml ?? 0} sem XML</small></div>
          <div class="k-err"><span>Crédito a incluir</span><b data-n="${rs.credito_incluir || 0}" data-fmt="brl">R$ 0,00</b><small>${rs.incluir ?? 0} nota(s) sem C197</small></div>
          <div class="k-err"><span>Crédito no C190 (indevido)</span><b data-n="${rs.credito_c190 || 0}" data-fmt="brl">R$ 0,00</b><small>${(rs.lugar_errado || 0) + (rs.sem_direito || 0)} nota(s) · retirar</small></div>
          <div class="k-warn"><span>C197 divergente</span><b data-n="${rs.divergente || 0}">0</b><small>${rs.divergencia < 0 ? 'lançado a mais' : 'lançado a menos'}: R$ ${fm(Math.abs(rs.divergencia || 0))}</small></div>
          <div class="k-ok"><span>Corretas</span><b data-n="${rs.ok || 0}">0</b><small>crédito permitido R$ ${fm(rs.credito_permitido)}</small></div>
          <div class="k-warn"><span>Pendentes de dado</span><b data-n="${(rs.sem_aliq || 0) + (rs.sem_xml || 0)}">0</b><small>${rs.sem_aliq ?? 0} sem alíquota · ${rs.sem_xml ?? 0} sem XML</small></div>
        </div>
        ${docs.length ? `
        <div class="sn-dash">
          <div class="sn-card">
            <div class="dif-k">Situação das notas do Simples</div>
            <div class="sn-bars">${grupos.map((g, i) => `
              <div class="sn-bar" style="--i:${i}">
                <span class="sn-bl">${SN_ST[g.k][0]}</span>
                <span class="sn-bt"><i style="--w:${(g.n / maxN * 100).toFixed(1)}%;background:${SN_ST[g.k][2]}"></i></span>
                <b>${g.n}</b><small>R$ ${fm(g.v)}</small>
              </div>`).join('')}</div>
          </div>
          <div class="sn-card">
            <div class="dif-k">Apuração (E110): antes × depois do que está marcado</div>
            <div id="snChart" class="sn-cmp"></div>
          </div>
        </div>
        <div class="chips sn-chips">
          <span class="chip ${SN.filtro === 'pend' ? 'on' : ''}" data-f="pend">Com pendência (${pend.length})</span>
          <span class="chip ${SN.filtro === 'todas' ? 'on' : ''}" data-f="todas">Todas (${docs.length})</span>
        </div>
        <div class="dif-tw sn-tw"><table class="dif-tab sn-tab">
          <thead><tr><th>Nota</th><th>Fornecedor (Simples)</th><th>CSOSN</th><th class="n">Base (valor)</th><th class="n">Alíq. Simples</th><th class="n">Crédito permitido</th>
            <th>No SPED hoje</th><th>O que será feito</th><th>Situação</th></tr></thead>
          <tbody>${docs.map(snLinha).join('')}</tbody>
        </table></div>` : `<div class="dif-av ok">Nenhuma nota de fornecedor do Simples Nacional encontrada entre as entradas com XML.</div>`}
        <div class="dif-foot">
          <div class="dif-prev" id="snPrev"></div>
          <div class="dif-e116">
            <div class="dif-k">Como fica no arquivo</div>
            <div class="sn-cod" id="snCod"></div>
            <div id="snE116" hidden>
              <div class="dif-k" style="margin-top:8px">Guia de ICMS (E116)</div>
              <p>O SPED não tem obrigação 000 e, com a correção, passa a haver ICMS a recolher. Informe a guia:</p>
              <label>Vencimento <input id="snVenc" placeholder="dd/mm/aaaa"></label>
              <label>Código de receita <input id="snCodRec" placeholder="ex.: 1210"></label>
            </div>
          </div>
          <div class="dif-acts"><button class="act inv-export sn-big" id="btnSnAplicar" style="background:#e23d4c;color:#fff;border-color:transparent">Aplicar no SPED (gera arquivo novo)</button></div>
        </div>
        <div id="snRes"></div>`;
      SN.temE116 = !!(an.e116 || []).find((x) => x.cod === '000');
      $('#btnSnFechar').addEventListener('click', snFechar);
      $('#btnSnXmls').addEventListener('click', snEscolherXmls);
      box.querySelectorAll('.sn-chips .chip').forEach((c) => c.addEventListener('click', () => { SN.filtro = c.dataset.f; snFiltra(); box.querySelectorAll('.sn-chips .chip').forEach((x) => x.classList.toggle('on', x === c)); }));
      box.querySelectorAll('input[data-sn]').forEach((el) => el.addEventListener('input', () => {
        if (el.dataset.sn === 'aliq') {
          const id = el.dataset.id, ck = box.querySelector(`input[data-sn="c197"][data-id="${id}"]`);
          if (ck && ck.disabled && num(el.value) > 0) { ck.disabled = false; ck.checked = true; }
        }
        snAtualiza();
      }));
      $('#btnSnAplicar').addEventListener('click', snAplicar);
      snFiltra();
      snAtualiza();
      animaNumeros(box);
    }

    function snLinha(d) {
      const st = SN_ST[d.status] || [d.status, 'b-mute'];
      const edit = snEditavel(d);
      const hoje = [];
      if (d.c190_icms > 0) hoje.push(`C190 com <b>R$ ${fm(d.c190_icms)}</b>`);
      if (d.c197 > 0) hoje.push(`C197 RO00000001 com <b>R$ ${fm(d.c197)}</b>`);
      const acoes = [];
      if (d.c190_icms > 0 && d.status !== 'sem_xml') acoes.push(`<label><input type="checkbox" data-sn="zerar" data-id="${d.id}" ${d.sug_zerar ? 'checked' : ''}> Zerar ICMS do C170/C190</label>`);
      if (d.status === 'sem_direito' && d.c197 > 0) acoes.push(`<label><input type="checkbox" data-sn="c197" data-id="${d.id}" checked> Retirar o C197</label>`);
      else if (edit) acoes.push(`<label><input type="checkbox" data-sn="c197" data-id="${d.id}" ${d.sug_c197 ? 'checked' : ''} ${d.status === 'sem_aliq' ? 'disabled' : ''}> ${d.c197 > 0 ? 'Substituir o C197' : 'Incluir C195 + C197'}</label>`);
      return `
        <tr data-snrow="${d.id}" data-st="${d.status}" class="${d.status === 'ok' || d.status === 'sem_xml' || d.status === 'uso_consumo' ? 'dif-off' : ''}">
          <td><b>${esc(d.num)}</b><small>${dt(d.data)}</small></td>
          <td>${esc(d.fornecedor)}<small>${esc(d.cnpj)}${d.uf ? ' · ' + esc(d.uf) : ''}</small></td>
          <td>${esc(d.csosn || '?')}</td>
          <td class="n">${d.base ? 'R$ ' + fm(d.base) : '—'}</td>
          <td class="n">${edit ? `<input class="sn-inp ${d.status === 'sem_aliq' ? 'req' : ''}" data-sn="aliq" data-id="${d.id}" value="${d.aliq ? fp(d.aliq) : ''}" placeholder="%">` : (d.aliq ? fp(d.aliq) : '—')}
            <small>${d.status === 'sem_aliq' ? 'conforme Anexo do fornecedor' : d.aliq_fonte === 'xml' ? 'pCredSN do XML' : d.aliq_fonte === 'cfop' ? 'CFOP sem direito' : d.status === 'sem_direito' ? 'CSOSN sem crédito' : ''}</small></td>
          <td class="n"><b data-snc="${d.id}">${d.credito ? 'R$ ' + fm(d.credito) : 'R$ 0,00'}</b></td>
          <td>${hoje.join('<br>') || '<span class="dif-mute">sem crédito</span>'}</td>
          <td class="sn-ac">${acoes.join('') || '—'}</td>
          <td><span class="dif-b ${st[1]}">${st[0]}</span>${(d.obs || []).map((o) => `<small class="dif-obs">${esc(o)}</small>`).join('')}</td>
        </tr>`;
    }

    function snFiltra() {
      $('#corrSimples').querySelectorAll('tr[data-snrow]').forEach((tr) => { tr.hidden = SN.filtro === 'pend' && (tr.dataset.st === 'ok' || tr.dataset.st === 'uso_consumo'); });
    }

    function snSelecao() {
      const box = $('#corrSimples'), out = [];
      let d06 = 0, d07 = 0, nZ = 0, n197 = 0, prim = null;
      for (const d of SN.an.docs || []) {
        const z = box.querySelector(`input[data-sn="zerar"][data-id="${d.id}"]`);
        const c = box.querySelector(`input[data-sn="c197"][data-id="${d.id}"]`);
        const ai = box.querySelector(`input[data-sn="aliq"][data-id="${d.id}"]`);
        const aliq = ai ? num(ai.value) : (d.status === 'sem_direito' ? 0 : d.aliq);
        const cred = d.status === 'sem_direito' ? 0 : snCredito(d, aliq);
        const cel = box.querySelector(`[data-snc="${d.id}"]`);
        if (cel && ai) cel.textContent = 'R$ ' + fm(cred);
        const zer = !!(z && z.checked), c197 = !!(c && c.checked && !c.disabled);
        if (zer) { d06 -= d.c190_icms; nZ++; }
        if (c197) { d07 += cred - d.c197; n197++; if (!prim && cred > 0) prim = { d, aliq, cred }; }
        if (zer || c197) out.push({ id: d.id, zerar: zer, c197, aliq: ai ? aliq : null });
      }
      return { docs: out, d06: r2(d06), d07: r2(d07), nZ, n197, prim };
    }

    function snAtualiza() {
      const an = SN.an, e = an.e110, sel = snSelecao();
      const b = $('#btnSnAplicar');
      b.disabled = !sel.docs.length; b.dataset.conf = ''; b.textContent = 'Aplicar no SPED (gera arquivo novo)';
      const obs = an.obs_existente || 'CSN';
      const cod = $('#snCod');
      if (cod) {
        cod.innerHTML = sel.prim ? `${an.obs_existente ? '' : `<span class="new">|0460|CSN|CRÉDITO SIMPLES NACIONAL|</span>  <i>← criado só uma vez</i>\n`}<span class="new">|C195|${esc(obs)}||</span>\n<span class="new">|C197|RO00000001|CONFORME NF Nº ${esc(sel.prim.d.num)}||${spf(sel.prim.d.base)}|${spf(sel.prim.aliq)}|${spf(sel.prim.cred)}||</span>\n<i>um C195 + C197 por nota, logo depois dos registros dela</i>`
          : '<i>Marque uma nota com C197 para ver as linhas.</i>';
      }
      const prev = $('#snPrev');
      if (!e) { prev.innerHTML = '<div class="dif-av err">SPED sem registro E110: não dá para lançar o crédito.</div>'; return; }
      const calc = (cr, aj) => {
        const expr = (e.deb + e.aj_deb + e.tot_aj_deb + e.est_cred) - (cr + aj + e.tot_aj_cred + e.est_deb + e.sld_ant);
        const sa = Math.max(0, expr);
        return { cr, aj, sa, rec: Math.max(0, sa - e.ded), sc: Math.max(0, -(expr - e.ded)) };
      };
      const A = calc(e.cred, e.aj_cred), D = calc(r2(e.cred + sel.d06), r2(e.aj_cred + sel.d07));
      const lin = (t, a, d) => `<tr><td>${t}</td><td class="n">R$ ${fm(a)}</td><td class="n ${r2(a) !== r2(d) ? 'mud' : ''}">R$ ${fm(d)}</td></tr>`;
      prev.innerHTML = `
        <div class="dif-k">Conferência da apuração (E110)</div>
        <p class="dif-sub">${sel.nZ} nota(s) com crédito retirado do C190 (R$ ${fm(-sel.d06)}) · ${sel.n197} nota(s) com C197 (diferença R$ ${fm(sel.d07)})</p>
        <table class="dif-mini"><thead><tr><th></th><th class="n">Antes</th><th class="n">Depois</th></tr></thead><tbody>
          ${lin('Créditos das notas (campo 06)', A.cr, D.cr)}
          ${lin('Ajustes a crédito das notas (campo 07)', A.aj, D.aj)}
          ${lin('Saldo devedor (campo 11)', A.sa, D.sa)}
          ${lin('ICMS a recolher (campo 13)', A.rec, D.rec)}
          ${lin('Saldo credor a transportar (campo 14)', A.sc, D.sc)}
        </tbody></table>
        ${r2(A.sc) !== r2(D.sc) ? '<p class="dif-warn">O saldo credor muda: o SPED do mês seguinte terá de receber o novo saldo credor anterior.</p>' : ''}`;
      SN.precisaE116 = !SN.temE116 && r2(D.rec) > 0 && r2(D.rec) !== r2(A.rec);
      $('#snE116').hidden = !SN.precisaE116;
      const ch = $('#snChart');
      if (ch) {
        const itens = [['Créditos (06)', A.cr, D.cr], ['Ajustes a crédito (07)', A.aj, D.aj], ['ICMS a recolher (13)', A.rec, D.rec]];
        const mx = Math.max(1, ...itens.flatMap((x) => [x[1], x[2]]));
        if (!ch.dataset.pronto) {
          ch.innerHTML = itens.map((x, i) => `
            <div class="sn-cg" style="--i:${i}"><span class="sn-bl">${x[0]}</span>
              <div class="sn-pair"><span class="sn-bt a"><i data-a="${i}"></i></span><em data-ta="${i}"></em></div>
              <div class="sn-pair"><span class="sn-bt d"><i data-d="${i}"></i></span><em data-td="${i}"></em></div></div>`).join('') +
            '<div class="leg sn-leg"><span><i style="background:#c9cfdc"></i>Antes</span><span><i style="background:#1f2a5a"></i>Depois</span></div>';
          ch.dataset.pronto = '1';
        }
        itens.forEach((x, i) => {
          ch.querySelector(`[data-a="${i}"]`).style.setProperty('--w', (x[1] / mx * 100).toFixed(2) + '%');
          ch.querySelector(`[data-d="${i}"]`).style.setProperty('--w', (x[2] / mx * 100).toFixed(2) + '%');
          ch.querySelector(`[data-ta="${i}"]`).textContent = 'R$ ' + fm(x[1]);
          const td = ch.querySelector(`[data-td="${i}"]`);
          td.textContent = 'R$ ' + fm(x[2]); td.classList.toggle('mud', r2(x[1]) !== r2(x[2]));
        });
      }
    }

    async function snAplicar() {
      const b = $('#btnSnAplicar'), sel = snSelecao();
      if (!sel.docs.length) return;
      const selecao = { docs: sel.docs };
      if (SN.precisaE116) {
        const venc = ($('#snVenc').value || '').replace(/\D/g, ''), cod = ($('#snCodRec').value || '').trim();
        if (venc.length !== 8 || !cod) { toast('Informe o vencimento (dd/mm/aaaa) e o código de receita da guia.', true); return; }
        selecao.e116 = { venc, cod_rec: cod };
      }
      if (b.dataset.conf !== '1') {
        const p = [];
        if (sel.n197) p.push(`${sel.n197} C197 (R$ ${fm(sel.d07)})`);
        if (sel.nZ) p.push(`retirar R$ ${fm(-sel.d06)} do C190`);
        b.dataset.conf = '1';
        b.textContent = `Confirmar: ${p.join(' · ')} (gera arquivo novo)`;
        return;
      }
      overlay(true, 'Lançando o crédito do Simples e recalculando E110, E116 e Bloco 9…');
      const res = await window.fiscocont.admin.simplesAplicar({ spedPath: corrSpedPath, usarCorrigido: corrFeito, xmls: XMLS.path, selecao });
      overlay(false);
      b.dataset.conf = ''; b.textContent = 'Aplicar no SPED (gera arquivo novo)';
      if (res.error) { toast(res.error, true); return; }
      corrFeito = true;
      const r = res.resumo || {}, ea = r.e110_antes, ed = r.e110_depois;
      const out = $('#snRes');
      out.innerHTML = `
        <div class="dif-done sn-done">
          <div class="dif-k">Lançado: arquivo novo gerado (o original não foi alterado)</div>
          <div class="dif-kpis sn-kpis">
            <div class="k-ok"><span>C197 RO00000001 incluídos</span><b data-n="${r.c197_inseridos || 0}">0</b><small>${r.c195_inseridos || 0} C195${r.c197_removidos ? ` · ${r.c197_removidos} C197 antigo(s) substituído(s)` : ''}</small></div>
            <div class="k-ok"><span>Crédito lançado no C197</span><b data-n="${r.credito_c197 || 0}" data-fmt="brl">R$ 0,00</b><small>${r.credito_c197_antes ? `antes R$ ${fm(r.credito_c197_antes)}` : 'campo 07 do E110'}</small></div>
            <div class="k-err"><span>Retirado do C190</span><b data-n="${r.credito_retirado_c190 || 0}" data-fmt="brl">R$ 0,00</b><small>${r.zeradas || 0} nota(s) · ${r.c170_zerados || 0} C170 · ${r.c190_zerados || 0} C190</small></div>
            ${ea && ed ? `<div><span>ICMS a recolher</span><b data-n="${ed.recolher}" data-fmt="brl">R$ 0,00</b><small>antes R$ ${fm(ea.recolher)}</small></div>` : ''}
          </div>
          ${(r.obs_0460_criados || []).length ? `<p class="dif-sub">Observação 0460 criada: ${r.obs_0460_criados.map(esc).join(', ')} · CRÉDITO SIMPLES NACIONAL</p>` : ''}
          ${r.e116 ? `<p class="dif-sub">${esc(r.e116)}</p>` : ''}
          ${(r.avisos || []).length ? `<div class="dif-av"><ul>${r.avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
          <div class="dif-acts">
            <button class="act inv-export" id="btnSnVer">Ver todos os dados (corrigido)</button>
            <button class="act inv-export" id="btnSnReconf">Conferir de novo</button>
            <button class="act inv-export sn-big" id="btnSnBaixar" style="background:#0ea472;color:#fff;border-color:transparent">Baixar SPED corrigido</button>
          </div>
        </div>`;
      animaNumeros(out);
      $('#btnSnBaixar').addEventListener('click', async () => {
        const r3 = await window.fiscocont.fiscal.baixarSpedCorrigido();
        if (r3.canceled) return;
        if (r3.error) { toast(r3.error, true); return; }
        toast('SPED corrigido salvo.');
        window.fiscocont.openPath(r3.path);
      });
      $('#btnSnVer').addEventListener('click', async () => {
        overlay(true, 'Lendo todos os dados do SPED corrigido…');
        const r2_ = await window.fiscocont.fiscal.visualizarSpedCorrigido();
        overlay(false);
        if (r2_.error) { toast(r2_.error, true); return; }
        const fr = $('#corrSpedFrame'); fr.srcdoc = r2_.html; fr.hidden = false;
        fr.scrollIntoView({ behavior: 'smooth' });
      });
      $('#btnSnReconf').addEventListener('click', () => snAnalisar());
      out.scrollIntoView({ behavior: 'smooth' });
      toast('Crédito do Simples lançado. Confira e baixe o SPED corrigido.');
    }
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
  // o processo principal recusou por trava: garante que a tela de senha apareça
  if (err && ROLE && /Sess[aã]o travada/i.test(String(msg))) { if (!SESSAO.travada) { SESSAO.travada = true; $('#lockErr').hidden = true; $('#lockSub').textContent = 'Por segurança, digite a sua senha para continuar de onde parou.'; } _mostraTrava(); }
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
  _atualizaTopo();
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

// Catálogo de módulos = itens do menu lateral (o Admin escolhe quais cada pessoa vê; o perfil é o ponto de partida).
function catalogoModulos() {
  const nomeGrupo = { fiscal: 'Fiscal', contabil: 'Contábil', 'admin-only': 'Administração' };
  return [...document.querySelectorAll('.nav .nav-item[data-view]')].map((b) => ({
    view: b.dataset.view, grupo: b.dataset.group, grupoNome: nomeGrupo[b.dataset.group] || b.dataset.group,
    nome: (b.querySelector('span') || b).textContent.trim(),
  }));
}
function modulosPadrao(perfil) {
  return catalogoModulos().filter((m) => (perfil === 'admin') || (perfil === 'fiscal' && m.grupo === 'fiscal')
    || (perfil === 'contabil' && m.grupo === 'contabil')).map((m) => m.view);
}
let MODULOS = null;      // null = padrão do perfil
function applyRole(role, modulos) {
  ROLE = role;
  if (modulos !== undefined) MODULOS = Array.isArray(modulos) ? modulos : null;
  const hideFiscal = role === 'contabil';
  const hideContabil = role === 'fiscal';
  const hideAdmin = role !== 'admin';
  $$('[data-group="fiscal"]').forEach((el) => el.classList.toggle('role-hidden', hideFiscal));
  $$('[data-group="contabil"]').forEach((el) => el.classList.toggle('role-hidden', hideContabil));
  $$('[data-group="admin-only"]').forEach((el) => el.classList.toggle('role-hidden', hideAdmin));
  // módulos liberados pelo Admin para esta pessoa (Admin vê tudo; Administração continua só para Admin)
  if (role !== 'admin' && MODULOS) {
    const ok = new Set(MODULOS);
    $$('.nav .nav-item[data-view]').forEach((b) => {
      const exclusivo = ['admin-usuarios', 'admin-lic'].includes(b.dataset.view);
      const sempre = b.dataset.view === 'manual-fiscal' && !hideFiscal;     // o manual vale para todo o Fiscal
      b.classList.toggle('role-hidden', exclusivo || (!sempre && !ok.has(b.dataset.view)));
    });
    // cada título do menu só aparece se algum item logo abaixo dele estiver liberado
    $$('.nav .nav-group').forEach((h) => {
      let el = h.nextElementSibling, algum = false;
      while (el && !el.classList.contains('nav-group')) {
        if (el.classList.contains('nav-item') && !el.classList.contains('role-hidden')) { algum = true; break; }
        el = el.nextElementSibling;
      }
      h.classList.toggle('role-hidden', !algum);
    });
  }
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

// ------------------------------------------------------------- login individual (e-mail e senha)
const SESSAO = { info: null, ultimoUso: Date.now(), travada: false, timer: null };
function _loginMsg(txt, ok) {
  const err = $('#loginErr'), okEl = $('#loginOk');
  err.hidden = true; okEl.hidden = true;
  if (!txt) return;
  const el = ok ? okEl : err;
  el.textContent = txt; el.hidden = false;
  if (!ok) { const card = document.querySelector('.login-card'); card.classList.remove('login-shake'); void card.offsetWidth; card.classList.add('login-shake'); }
}
function _mostraLogin() {
  ROLE = null; SESSAO.info = null; SESSAO.travada = false;
  if (window.fechSair) window.fechSair();
  if (window._manualSair) window._manualSair();
  $('#lockCard').hidden = true;
  document.querySelector('.login-card').hidden = false;
  $('#loginGate').style.display = 'flex';
  $('#loginPass').value = ''; delete $('#loginPass').dataset.salva;
  const ut = $('#userTag'); if (ut) ut.textContent = '';
  setTimeout(() => ($('#loginEmail').value ? $('#loginPass') : $('#loginEmail')).focus(), 50);
}
let _senhaPendente = null;
function _pedeSenhaNova(res) {
  _senhaPendente = res;
  document.querySelector('.login-card').hidden = true;
  $('#lockCard').hidden = true; $('#licenseCard').hidden = true;
  $('#senhaCard').hidden = false; $('#senhaErr').hidden = true;
  $('#senhaNova').value = ''; $('#senhaConf').value = '';
  $('#senhaSub').textContent = `${(res.sessao || {}).nome || ''}, você entrou com uma senha provisória. Crie agora a sua senha pessoal: só você vai saber.`;
  _senhaRegras();
  setTimeout(() => $('#senhaNova').focus(), 50);
}
function _senhaRegras() {
  const n = $('#senhaNova').value, c = $('#senhaConf').value;
  const ok = { tam: n.length >= 8, let: /[A-Za-z]/.test(n), num: /[0-9]/.test(n), igual: !!n && n === c };
  $$('#senhaRegras span').forEach((sp) => sp.classList.toggle('ok', !!ok[sp.dataset.r]));
  return Object.values(ok).every(Boolean);
}
function _entrou(res) {
  if (res.sessao && res.sessao.trocarSenha) { _pedeSenhaNova(res); return; }
  $('#senhaCard').hidden = true; document.querySelector('.login-card').hidden = false;
  SESSAO.info = res.sessao || null;
  SESSAO.ultimoUso = Date.now(); SESSAO.travada = false;
  try { localStorage.setItem('fc_ultimo_email', (res.sessao || {}).email || ''); } catch (_) {}
  _loginMsg('');
  $('#loginGate').style.display = 'none';
  const ut = $('#userTag');
  if (ut && SESSAO.info) ut.textContent = `${SESSAO.info.nome} · ${({ admin: 'Admin', fiscal: 'Fiscal', contabil: 'Contábil' })[SESSAO.info.perfil] || ''}${SESSAO.info.offline ? ' · sem internet' : ''}`;
  applyRole(res.role, (res.sessao || {}).modulos || null);
  if (res.aviso) toast(res.aviso);
  verificarNovidades();
}
// trava por inatividade: 40 min (Admin) / 60 min (demais) sem mexer no sistema
function _travar() {
  if (!ROLE || SESSAO.travada) return;
  SESSAO.travada = true;
  window.fiscocont.auth.travar();
  $('#lockErr').hidden = true;
  $('#lockSub').textContent = `${(SESSAO.info || {}).nome || ''}, o sistema ficou ${(SESSAO.info || {}).travaMin || 60} minutos sem uso. Digite a sua senha para continuar de onde parou.`;
  _mostraTrava();
}
// Mostra a tela de senha da trava. Achado real (23/10): a checagem da licença (a cada 15 min e em tempo real)
// escondia a tela inteira por cima da trava — o sistema ficava travado, mas sem onde digitar a senha.
function _mostraTrava() {
  if (!SESSAO.travada) return;
  document.querySelector('.login-card').hidden = true;
  $('#licenseCard').hidden = true;
  const sc = $('#senhaCard'); if (sc) sc.hidden = true;
  $('#lockCard').hidden = false;
  $('#loginGate').style.display = 'flex';
  setTimeout(() => $('#lockPass').focus(), 50);
}
function _vigiaInatividade() {
  const uso = () => { if (!SESSAO.travada) SESSAO.ultimoUso = Date.now(); };
  ['mousemove', 'mousedown', 'keydown', 'wheel', 'touchstart'].forEach((ev) => window.addEventListener(ev, uso, { passive: true }));
  setInterval(() => {
    if (ROLE && SESSAO.travada && $('#loginGate').style.display === 'none' && $('#licenseCard').hidden) { _mostraTrava(); return; }
    if (!ROLE || SESSAO.travada || !SESSAO.info) return;
    if (Date.now() - SESSAO.ultimoUso > (SESSAO.info.travaMin || 60) * 60000) _travar();
  }, 20000);
}
// ---------------------------------------------------------------- tela de atualização
// 1) baixando (com progresso) · 2) pronta: "Atualizar e reiniciar" ou "Mais tarde" · 3) encerrando → o instalador
// mostra a janelinha de progresso e o sistema reabre sozinho. "Mais tarde" instala ao fechar o sistema.
function _updNotas(html) {
  const tmp = document.createElement('div');
  tmp.innerHTML = String(html || '');
  let itens = [...tmp.querySelectorAll('li')].map((li) => li.textContent.trim()).filter(Boolean);
  if (!itens.length) {   // veio como texto (markdown): pega as linhas "- item"
    itens = String(html || '').split(/\r?\n/).map((l) => l.trim()).filter((l) => /^[-*•]\s+/.test(l))
      .map((l) => l.replace(/^[-*•]\s+/, '').replace(/\*\*/g, '').trim());
  }
  return itens.slice(0, 12);
}
function bindAtualizacao() {
  const up = window.fiscocont && window.fiscocont.updater;
  if (!up) return;
  const st = { versao: '', atual: '', pronta: false, fechada: false, instalando: false };
  const m = $('#updModal');
  const mb = (n) => (n / 1048576).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const banner = (txt, botao) => {
    $('#updateBannerText').textContent = txt;
    $('#updateBannerBtn').textContent = botao;
    $('#updateBanner').hidden = false;
  };
  const versoes = () => {
    $('#updDe').textContent = st.atual ? 'v' + st.atual : '';
    $('#updPara').textContent = 'v' + st.versao;
    $('#updStepVer').textContent = 'v' + st.versao;
  };
  const novidades = (notas) => {
    const itens = _updNotas(notas);
    if (!itens.length) return;
    $('#updNovLista').innerHTML = itens.map((t) => `<li>${_esc(t)}</li>`).join('');
    $('#updNov').hidden = false;
  };
  const abrir = () => { m.hidden = false; $('#updateBanner').hidden = true; };

  up.onAvailable((d) => {
    st.versao = d.versao || ''; st.atual = d.atual || ''; versoes(); novidades(d.notas);
    $('#updIc').className = 'upd-ic'; $('#updIc').textContent = '⬇';
    $('#updTit').textContent = 'Baixando atualização';
    $('#updSub').textContent = 'Pode continuar trabalhando enquanto baixa.';
    $('#updBaixa').hidden = false;
    if (!st.fechada) abrir(); else banner(`Baixando a versão v${st.versao}…`, 'Ver');
  });
  up.onProgress && up.onProgress((p) => {
    if (st.pronta) return;
    const pct = Math.max(0, Math.min(100, p.pct || 0));
    $('#updBar').style.width = pct.toFixed(1) + '%';
    $('#updPct').innerHTML = `<b>${Math.floor(pct)}%</b>` + (p.total ? ` · ${mb(p.feito)} de ${mb(p.total)} MB` : '');
    const resta = p.vel > 0 && p.total ? Math.max(1, Math.round((p.total - p.feito) / p.vel)) : 0;
    $('#updVel').textContent = p.vel > 0 ? `${mb(p.vel)} MB/s` + (resta ? ` · ~${resta < 60 ? resta + ' s' : Math.round(resta / 60) + ' min'}` : '') : '';
    if (m.hidden && !$('#updateBanner').hidden) banner(`Baixando a versão v${st.versao} · ${Math.floor(pct)}%`, 'Ver');
  });
  up.onReady((d) => {
    st.pronta = true; st.versao = d.versao || st.versao; st.atual = d.atual || st.atual; versoes();
    if ($('#updNov').hidden) novidades(d.notas);
    $('#updIc').className = 'upd-ic ok'; $('#updIc').textContent = '✓';
    $('#updTit').textContent = 'Atualização pronta';
    $('#updSub').innerHTML = 'O FiscoCont+ fecha, instala e <b>abre de novo sozinho</b>.';
    $('#updBaixa').hidden = true; $('#updAviso').hidden = false; $('#updRod').hidden = false;
    $('#updAgora').hidden = false; $('#updDepois').textContent = 'Mais tarde';
    abrir();   // mesmo que tenha fechado durante o download: agora precisa da decisão
  });

  $('#updDepois').addEventListener('click', () => {
    if (st.instalando) return;
    m.hidden = true; st.fechada = true;
    if (st.pronta) banner(`Versão v${st.versao} pronta. Instala quando você fechar o sistema.`, 'Atualizar agora');
    else banner(`Baixando a versão v${st.versao}…`, 'Ver');
  });
  $('#updAgora').addEventListener('click', () => {
    if (st.instalando || !st.pronta) return;
    st.instalando = true;
    $('#updIc').className = 'upd-ic go'; $('#updIc').textContent = '↻';
    $('#updTit').textContent = 'Atualizando o FiscoCont+';
    $('#updSub').textContent = 'Não desligue o computador. O sistema volta sozinho.';
    $('#updNov').hidden = true; $('#updAviso').hidden = true; $('#updRod').hidden = true; $('#updBts').hidden = true;
    $('#updSteps').hidden = false;
    setTimeout(() => up.installNow(st.versao), 1600);   // dá tempo de ler; depois a janelinha "Atualizando…" fica na tela até reabrir
  });
  $('#updateBannerBtn').addEventListener('click', abrir);
}

// ---------------------------------------------------------------- Manual do Fiscal
// Leitura dentro do sistema: as páginas chegam da nuvem como imagem e são desenhadas num canvas (não há arquivo,
// texto para copiar nem "salvar imagem"). Enquanto a tela está aberta: sem botão direito, sem Ctrl+S/P/C/A, e a
// janela fica protegida contra print e gravação de tela (main.js). Cada abertura é registrada para o Admin.
function bindManual() {
  const api = window.fiscocont && window.fiscocont.manual;
  if (!api || !$('#view-manual-fiscal')) return;
  const M = { info: null, pag: 1, zoom: 1, cache: new Map(), aberto: false, acesso: '', t0: 0, desenhando: 0, sum: true, fit: false };
  try { const pr = JSON.parse(localStorage.getItem('mfPref') || '{}'); if (pr.sum === false) M.sum = false; if (pr.fit) M.fit = true; } catch (_) {}
  const salvaPref = () => { try { localStorage.setItem('mfPref', JSON.stringify({ sum: M.sum, fit: M.fit })); } catch (_) {} };
  function aplicaModo() {
    $('#mfTgSum').classList.toggle('on', M.sum); $('#mfTgFit').classList.toggle('on', M.fit);
    $('#view-manual-fiscal .mf-body').classList.toggle('sem-sum', !M.sum);
  }
  const cv = $('#mfCanvas'), view = $('#mfView');
  const PARTES = { 1: 'Fundamentos', 2: 'Rotina mensal', 3: 'FiscoCont+ no dia a dia', 4: 'Anexos' };

  const rotulo = (i) => (i <= 1 ? 'Capa' : `${i - 1} / ${(M.info.total || 1) - 1}`);
  function toc() {
    const termo = ($('#mfBusca').value || '').trim().toLowerCase();
    let h = '', parte = 0;
    const atual = [...(M.info.capitulos || [])].reverse().find((c) => c.pagina <= M.pag);
    for (const c of M.info.capitulos || []) {
      if (termo && !(`${c.n} ${c.titulo}`).toLowerCase().includes(termo)) continue;
      if (c.parte !== parte) { parte = c.parte; h += `<div class="mf-tp">Parte ${c.parte} · ${_esc(c.parteNome || PARTES[c.parte] || '')}</div>`; }
      h += `<div class="mf-ti${atual && atual.n === c.n ? ' on' : ''}" data-p="${c.pagina}"><em>${String(c.n).padStart(2, '0')}</em>${_esc(c.titulo)}</div>`;
    }
    $('#mfToc').innerHTML = h || '<div class="mf-vazio" style="margin:12px 4px">Nenhum capítulo encontrado.</div>';
  }
  async function img(i) {
    if (M.cache.has(i)) return M.cache.get(i);
    const pr = api.pagina(i).then((r) => {
      if (r.error) throw new Error(r.error);
      return new Promise((ok, err) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => err(new Error('Página inválida.')); im.src = 'data:image/jpeg;base64,' + r.img; });
    });
    M.cache.set(i, pr);
    pr.catch(() => M.cache.delete(i));
    return pr;
  }
  async function desenha() {
    if (!M.info) return;
    const meu = ++M.desenhando;
    $('#mfPag').textContent = rotulo(M.pag);
    $('#mfZoom').textContent = Math.round(M.zoom * 100) + '%';
    toc();
    try {
      const im = await img(M.pag);
      if (meu !== M.desenhando) return;
      const base = M.fit ? Math.max(480, view.clientWidth - 48) : Math.min(860, Math.max(520, view.clientWidth - 60));
      const w = Math.round(base * M.zoom), hgt = Math.round(w * im.height / im.width);
      const dpr = window.devicePixelRatio || 1;
      cv.width = Math.round(w * dpr); cv.height = Math.round(hgt * dpr);
      cv.style.width = w + 'px'; cv.style.height = hgt + 'px';
      const ctx = cv.getContext('2d');
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(im, 0, 0, cv.width, cv.height);
      view.scrollTop = 0;
      if (M.pag < M.info.total) img(M.pag + 1).catch(() => {});   // já vai buscando a próxima
    } catch (e) { toast(String(e.message || e), true); }
  }
  const ir = (i) => { if (!M.info) return; M.pag = Math.max(1, Math.min(M.info.total, i)); desenha(); };

  window._manualEntrar = async () => {
    if (M.aberto) return;
    M.aberto = true;      // abre na capa quando o sistema é aberto; durante o uso, volta na página em que parou
    aplicaModo();
    api.protecao(true);
    $('#mfAdm').hidden = ROLE !== 'admin';
    if (!M.info) {
      const r = await api.info();
      if (r.error || r.vazio) {
        cv.hidden = true; $('#mfVazio').hidden = false;
        $('#mfVazio').textContent = r.error ? r.error : (ROLE === 'admin' ? 'O manual ainda não foi publicado. Use "Publicar manual" e escolha a pasta do manual.' : 'O manual ainda não está disponível.');
        $('#mfPag').textContent = '—';
        return;
      }
      M.info = r; cv.hidden = false; $('#mfVazio').hidden = true;
    }
    desenha();
    M.t0 = Date.now(); M.acesso = '';
    api.acessoInicio().then((r) => { if (r && r.id) M.acesso = r.id; }).catch(() => {});
  };
  window._manualSair = () => {
    if (!M.aberto) return;
    M.aberto = false;
    api.protecao(false);
    if (M.acesso) api.acessoFim(M.acesso, (Date.now() - M.t0) / 1000).catch(() => {});
    M.acesso = '';
  };
  window.addEventListener('beforeunload', () => window._manualSair && window._manualSair());

  $('#mfInicio').addEventListener('click', () => ir(1));
  $('#mfAnt').addEventListener('click', () => ir(M.pag - 1));
  $('#mfProx').addEventListener('click', () => ir(M.pag + 1));
  $('#mfMenos').addEventListener('click', () => { M.zoom = Math.max(0.6, +(M.zoom - 0.1).toFixed(2)); desenha(); });
  $('#mfMais').addEventListener('click', () => { M.zoom = Math.min(2, +(M.zoom + 0.1).toFixed(2)); desenha(); });
  $('#mfToc').addEventListener('click', (ev) => { const t = ev.target.closest('.mf-ti'); if (t) ir(Number(t.dataset.p)); });
  $('#mfBusca').addEventListener('input', toc);
  $('#mfTgSum').addEventListener('click', () => { M.sum = !M.sum; aplicaModo(); salvaPref(); desenha(); });
  $('#mfTgFit').addEventListener('click', () => { M.fit = !M.fit; if (M.fit) M.sum = false; M.zoom = 1; aplicaModo(); salvaPref(); desenha(); });
  window.addEventListener('resize', () => { if (M.aberto) desenha(); });

  // sem botão direito, arrastar, copiar ou atalhos de salvar/imprimir enquanto o manual está na tela
  const naTela = () => M.aberto && !$('#view-manual-fiscal').hidden;
  ['contextmenu', 'dragstart', 'copy', 'cut', 'selectstart'].forEach((tipo) =>
    $('#view-manual-fiscal').addEventListener(tipo, (ev) => { if (ev.target.id !== 'mfBusca') ev.preventDefault(); }));
  document.addEventListener('keydown', (ev) => {
    if (!naTela()) return;
    const k = (ev.key || '').toLowerCase(), ctrl = ev.ctrlKey || ev.metaKey;
    if (ctrl && ['s', 'p', 'c', 'a', 'u'].includes(k) && ev.target.id !== 'mfBusca') { ev.preventDefault(); ev.stopPropagation(); return; }
    if (k === 'printscreen') { ev.preventDefault(); return; }
    if (ev.target.id === 'mfBusca') return;
    if (k === 'arrowright' || k === 'pagedown') { ev.preventDefault(); ir(M.pag + 1); }
    if (k === 'arrowleft' || k === 'pageup') { ev.preventDefault(); ir(M.pag - 1); }
  }, true);

  // Admin: publicar/trocar o manual e ver quem abriu
  $('#mfPublicar').addEventListener('click', async () => {
    overlay(true, 'Publicando o manual…');
    const r = await api.publicar();
    overlay(false);
    if (r.error) { toast(r.error, true); return; }
    if (r.cancelado) return;
    M.info = null; M.cache.clear(); M.pag = 1;
    toast(`Manual publicado: ${r.total} páginas.`);
    window._manualSair(); window._manualEntrar();
  });
  $('#mfAcessos').addEventListener('click', async () => {
    const r = await api.acessos();
    if (r.error) { toast(r.error, true); return; }
    const fmt = (iso) => { if (!iso) return '—'; const d = new Date(iso); return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }); };
    const dur = (s) => (s >= 60 ? Math.round(s / 60) + ' min' : (s ? s + ' s' : '—'));
    $('#mfAcLista').innerHTML = (r.lista || []).length
      ? `<table><thead><tr><th>Usuário</th><th>Abriu em</th><th>Tempo</th></tr></thead><tbody>${r.lista.map((a) => `<tr><td>${_esc(a.nome || a.email)}</td><td>${fmt(a.inicio)}</td><td>${dur(a.segundos)}</td></tr>`).join('')}</tbody></table>`
      : '<div class="upd-sub" style="margin-top:10px">Ninguém abriu o manual ainda.</div>';
    $('#mfAcModal').hidden = false;
  });
  $('#mfAcFechar').addEventListener('click', () => { $('#mfAcModal').hidden = true; });
}

// ---------------------------------------------------------------- Consulta Manifestação NF-e
// Só consulta (nada é enviado à SEFAZ). Botão nas Baixas DF-e, para toda a equipe.
function chaveNfeValida(ch) {
  if (!/^\d{44}$/.test(ch)) return false;
  let soma = 0, peso = 2;
  for (let i = 42; i >= 0; i--) { soma += Number(ch[i]) * peso; peso = peso === 9 ? 2 : peso + 1; }
  const dv = 11 - (soma % 11);
  return Number(ch[43]) === (dv >= 10 ? 0 : dv);
}
function bindManifestacao() {
  const api = window.fiscocont && window.fiscocont.manif;
  if (!api || !$('#view-fiscal-manifestacao')) return;
  const TIPOS = [
    ['confirmada', 'Confirmada', '#16a34a', 'ok'], ['ciencia', 'Só ciência', '#f59e0b', 'am'], ['nenhuma', 'Sem manifestação', '#94a3b8', 'cz'],
    ['desconhecida', 'Desconhecida', '#dc2626', 'er'], ['nao_realizada', 'Operação não realizada', '#7c3aed', 'ro'],
  ];
  const SIT = { autorizada: ['Autorizada', 'ok'], cancelada: ['Cancelada', 'er'], denegada: ['Denegada', 'er'], nao_encontrada: ['Não encontrada', 'cz'], erro: ['Erro na consulta', 'cz'] };
  const S = { empresas: [], empresa: null, validas: [], res: null, filtro: 'todas' };
  const brl = (v) => Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const cnpjFmt = (d) => (d && d.length === 14 ? `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}` : d || '');
  const dataBr = (s) => (s && s.length >= 10 ? s.slice(0, 10).split('-').reverse().join('/') : '');

  $('#btnMnAbrir').addEventListener('click', () => switchView('fiscal-manifestacao'));
  $('#mnVoltar').addEventListener('click', () => switchView('fiscal-downloads'));
  $('#btnMnAbrir').hidden = false;      // liberado para toda a equipe que usa as Baixas DF-e

  async function carregaEmpresas() {
    const r = await api.empresas();
    if (r.error) { toast(r.error, true); return; }
    S.empresas = r.empresas || [];
    $('#mnEmpresasLista').innerHTML = S.empresas.map((e) => `<option value="${_esc(e.nome)} · ${cnpjFmt(e.cnpj)}">`).join('');
    checaEmpresa();
  }
  function checaEmpresa() {
    const txt = $('#mnEmpresa').value;
    const dig = txt.replace(/\D/g, '');
    let emp = null;
    const cn = dig.length >= 14 ? dig.slice(-14) : '';
    if (cn) emp = S.empresas.find((e) => e.cnpj === cn);
    if (!emp && txt.trim().length >= 3 && !cn) emp = S.empresas.find((e) => e.nome.toLowerCase() === txt.trim().toLowerCase());
    S.empresa = null;
    $('#mnAlerta').hidden = true; $('#mnEmpOk').hidden = true;
    if (emp && emp.vencido) {
      $('#mnAlertaTit').textContent = 'O certificado desta empresa está vencido';
      $('#mnAlertaTxt').textContent = `Válido até ${dataBr(emp.validade)}. Cadastre o certificado novo nas Baixas DF-e para consultar.`;
      $('#mnAlerta').hidden = false;
    } else if (emp) {
      S.empresa = emp;
      $('#mnEmpOk').textContent = `✓ Certificado cadastrado · válido até ${dataBr(emp.validade) || '—'}`;
      $('#mnEmpOk').hidden = false;
    } else if (cn) {
      $('#mnAlertaTit').textContent = 'Certificado desta empresa não está cadastrado';
      $('#mnAlertaTxt').textContent = `Para consultar a manifestação é preciso o certificado A1 da empresa destinatária (${cnpjFmt(cn)}). Cadastre agora: as chaves que você colou continuam aqui.`;
      $('#mnAlerta').hidden = false;
    }
    atualizaBotao();
  }
  function checaChaves() {
    const linhas = $('#mnChaves').value.split(/\r?\n/);
    const vistos = new Set(); const ruins = []; let dup = 0;
    linhas.forEach((l, i) => {
      const achadas = l.replace(/[\s.\-/]/g, '').match(/\d{44}/g);
      if (!achadas) { const d = l.replace(/\D/g, ''); if (d) ruins.push(`Linha ${i + 1}: ${d.length} dígitos (a chave tem 44)`); return; }
      achadas.forEach((c) => {
        if (vistos.has(c)) { dup++; return; }
        if (!chaveNfeValida(c)) { ruins.push(`Linha ${i + 1}: ${c} — dígito verificador não confere`); return; }
        vistos.add(c);
      });
    });
    S.validas = [...vistos];
    $('#mnQtdOk').textContent = `${S.validas.length} chave${S.validas.length === 1 ? '' : 's'} válida${S.validas.length === 1 ? '' : 's'}`;
    $('#mnQtdErr').hidden = !ruins.length; $('#mnQtdErr').textContent = `${ruins.length} inválida${ruins.length === 1 ? '' : 's'}`;
    $('#mnQtdDup').hidden = !dup; $('#mnQtdDup').textContent = `${dup} repetida${dup === 1 ? '' : 's'} (ignorada${dup === 1 ? '' : 's'})`;
    $('#mnRuins').hidden = !ruins.length; $('#mnRuins').innerHTML = ruins.slice(0, 50).map(_esc).join('<br>');
    atualizaBotao();
  }
  function atualizaBotao() {
    const b = $('#mnConsultar');
    b.disabled = !(S.empresa && S.validas.length);
    b.textContent = S.validas.length ? `Consultar ${S.validas.length} nota${S.validas.length === 1 ? '' : 's'}` : 'Consultar';
  }
  $('#mnEmpresa').addEventListener('input', checaEmpresa);
  $('#mnChaves').addEventListener('input', checaChaves);
  $('#mnOutra').addEventListener('click', () => { $('#mnEmpresa').value = ''; checaEmpresa(); $('#mnEmpresa').focus(); });
  $('#mnCadastrar').addEventListener('click', () => {
    window._manifPendente = () => { window._manifPendente = null; switchView('fiscal-manifestacao'); };
    switchView('fiscal-downloads');
    setTimeout(() => $('#btnDlCadastrarCert').click(), 50);
  });
  $('#mnImportar').addEventListener('click', async () => {
    const r = await api.importarChaves();
    if (r.error) { toast(r.error, true); return; }
    if (r.cancelado) return;
    const atual = $('#mnChaves').value.trim();
    $('#mnChaves').value = (atual ? atual + '\n' : '') + (r.chaves || []).join('\n');
    checaChaves();
    toast(`${(r.chaves || []).length} chave(s) encontrada(s) no arquivo.`);
  });

  const mostraForm = (sim) => {
    $('#mnForm').hidden = !sim; $('#mnRes').hidden = sim || !S.res;
    $('#mnCancelar').hidden = !S.res;
    ['#mnXlsx', '#mnHtml', '#mnNova'].forEach((x) => { $(x).hidden = sim || !S.res; });
  };
  $('#mnNova').addEventListener('click', () => mostraForm(true));
  $('#mnCancelar').addEventListener('click', () => mostraForm(false));

  api.onProgresso((d) => {
    const pct = d.total ? Math.round(100 * d.feitas / d.total) : 0;
    $('#mnProgBar').style.width = pct + '%';
    $('#mnProgTxt').textContent = `${d.feitas} de ${d.total} consultadas na SEFAZ` + (d.guardadas ? ` · ${d.guardadas} já estavam guardadas` : '');
  });
  async function consultar(chaves) {
    $('#mnProgBar').style.width = '0%'; $('#mnProgTxt').textContent = 'Preparando…'; $('#mnProg').hidden = false;
    const r = await api.consultar(S.empresa.id, chaves);
    $('#mnProg').hidden = true;
    if (r.error) { toast(r.error, true); return; }
    S.res = r; S.filtro = 'todas';
    desenha(); mostraForm(false);
  }
  $('#mnConsultar').addEventListener('click', () => { if (S.empresa && S.validas.length) consultar(S.validas); });

  function donut(cont, total) {
    const r = 70, c = 2 * Math.PI * r; let off = 0;
    let s = `<svg width="180" height="180" viewBox="0 0 180 180"><circle cx="90" cy="90" r="${r}" fill="none" stroke="var(--line)" stroke-width="24"/>`;
    for (const [k, , cor] of TIPOS) {
      const q = cont[k] || 0; if (!q) continue;
      const L = c * q / total;
      s += `<circle cx="90" cy="90" r="${r}" fill="none" stroke="${cor}" stroke-width="24" stroke-dasharray="${Math.max(L - 2, 1).toFixed(1)} ${c.toFixed(1)}" stroke-dashoffset="${(-off).toFixed(1)}" transform="rotate(-90 90 90)"/>`;
      off += L;
    }
    return s + `<text x="90" y="88" text-anchor="middle" font-size="28" font-weight="800" fill="currentColor">${total}</text><text x="90" y="108" text-anchor="middle" font-size="11" fill="#64748b">notas consultadas</text></svg>`;
  }
  const manifDe = (i) => (['cancelada', 'denegada', 'nao_encontrada', 'erro'].includes(i.situacao) ? '' : (i.manifestacao || 'nenhuma'));
  function linhaManif(i) {
    const m = manifDe(i);
    if (!m) return `<span class="mn-st cz">—</span>${i.situacao === 'cancelada' ? '<span class="mn-mini" style="color:#b91c1c">não escriturar / estornar</span>' : ''}`;
    const t = TIPOS.find((x) => x[0] === m);
    return `<span class="mn-st ${t[3]}">${t[1]}</span>`;
  }
  function linhaData(i) {
    const m = manifDe(i);
    if ((m === 'nenhuma' || m === 'ciencia') && typeof i.prazo_dias === 'number') {
      const cor = i.prazo_dias <= 15 ? '#b91c1c' : (i.prazo_dias <= 60 ? '#b45309' : 'inherit');
      return (m === 'ciencia' ? `ciência em ${dataBr(i.dh_manifestacao)}<br>` : '') + `<b style="color:${cor}">${i.prazo_dias > 0 ? `faltam ${i.prazo_dias} dias` : 'prazo vencido'}</b>`;
    }
    return dataBr(i.dh_manifestacao) || '—';
  }
  function filtrados() {
    const it = S.res.itens || [];
    if (S.filtro === 'todas') return it;
    if (S.filtro === 'canceladas') return it.filter((i) => i.situacao === 'cancelada' || i.situacao === 'denegada');
    if (S.filtro === 'erros') return it.filter((i) => i.situacao === 'erro' || i.situacao === 'nao_encontrada');
    return it.filter((i) => manifDe(i) === S.filtro);
  }
  function desenha() {
    const r = S.res, it = r.itens || [];
    const cont = {}, val = {};
    it.forEach((i) => { const m = manifDe(i); if (!m) return; cont[m] = (cont[m] || 0) + 1; if (i.valor) val[m] = (val[m] || 0) + Number(i.valor); });
    const comManif = it.filter((i) => manifDe(i)).length;
    const nAut = it.filter((i) => i.situacao === 'autorizada').length, nCan = it.filter((i) => i.situacao === 'cancelada').length,
      nDen = it.filter((i) => i.situacao === 'denegada').length, nErr = it.filter((i) => i.situacao === 'erro' || i.situacao === 'nao_encontrada').length;
    const venc = r.empresa.validade ? `certificado válido até ${dataBr(r.empresa.validade)}` : '';
    $('#mnQry').innerHTML = `Destinatário <b>${_esc(r.empresa.nome)} · ${cnpjFmt(r.empresa.cnpj)}</b>${venc ? `<span class="tag">${venc}</span>` : ''}<span style="margin-left:auto">${it.length} chave${it.length === 1 ? '' : 's'} · consultado em ${new Date(r.quando).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}</span>`;
    $('#mnErros').hidden = !nErr;
    $('#mnErros').innerHTML = nErr ? `⚠ <span><b>${nErr} nota${nErr === 1 ? '' : 's'} não encontrada${nErr === 1 ? '' : 's'} ou sem resposta da SEFAZ.</b> Veja o motivo na tabela (filtro "Erros") e confira a chave no Portal da NF-e.</span> <button class="mn-sec" id="mnRefazer" style="margin-left:auto">Consultar essas de novo</button>` : '';
    if (nErr) $('#mnRefazer').onclick = () => consultar(it.filter((i) => i.situacao === 'erro' || i.situacao === 'nao_encontrada').map((i) => i.chave));
    $('#mnKpis').innerHTML = TIPOS.map(([k, n, cor]) => `<div class="mn-k" style="--c:${cor}" data-f="${k}"><span>${n}</span><b>${cont[k] || 0}</b><em>${val[k] ? 'R$ ' + brl(val[k]) : (cont[k] ? 'valor indisponível' : '—')}</em></div>`).join('');
    $('#mnDonut').innerHTML = comManif ? donut(cont, comManif) + `<div class="mn-lg">${TIPOS.map(([k, n, cor]) => `<div><i style="background:${cor}"></i>${n}<b>${cont[k] || 0}</b><span>${comManif ? Math.round(100 * (cont[k] || 0) / comManif) : 0}%</span></div>`).join('')}</div>` : '<div class="mn-sub">Nenhuma nota autorizada para mostrar.</div>';
    const tot = Math.max(1, nAut + nCan + nDen);
    $('#mnSit').innerHTML = `<div class="mn-sitbar"><div style="width:${100 * nAut / tot}%;background:#16a34a"></div><div style="width:${100 * nCan / tot}%;background:#dc2626"></div><div style="width:${100 * nDen / tot}%;background:#7f1d1d"></div></div>
      <div class="mn-big"><div><b>${nAut}</b>Autorizadas</div><div><b style="color:${nCan ? '#dc2626' : 'inherit'}">${nCan}</b>Canceladas</div><div><b>${nDen}</b>Denegadas</div></div>
      ${nCan ? `<div class="mn-al">⚠ <b>${nCan} nota${nCan === 1 ? '' : 's'} cancelada${nCan === 1 ? '' : 's'} pelo emitente.</b> Se estiver${nCan === 1 ? '' : 'em'} escriturada${nCan === 1 ? '' : 's'}, precisa${nCan === 1 ? '' : 'm'} ser estornada${nCan === 1 ? '' : 's'} (risco de crédito indevido).</div>` : ''}`;
    const pend = it.filter((i) => ['nenhuma', 'ciencia'].includes(manifDe(i)) && typeof i.prazo_dias === 'number').sort((a, b) => a.prazo_dias - b.prazo_dias);
    $('#mnPrazos').innerHTML = pend.length ? pend.slice(0, 6).map((i) => {
      const d = i.prazo_dias, cor = d <= 15 ? '#dc2626' : (d <= 60 ? '#f59e0b' : '#94a3b8');
      return `<div class="mn-pz"><div class="mn-pzt"><span>NF ${_esc(i.numero)} · ${_esc(i.emitente || cnpjFmt(i.cnpj_emit))}</span><b style="color:${cor}">${d > 0 ? `faltam ${d} dias` : 'vencido'}</b></div><div class="mn-pzb"><div style="width:${Math.min(100, Math.max(3, (180 - d) / 180 * 100))}%;background:${cor}"></div></div></div>`;
    }).join('') + (pend.length > 6 ? `<div class="mn-sub">+ ${pend.length - 6} nota(s) na tabela</div>` : '') + '<div class="mn-sub" style="margin-top:8px">O prazo conta 180 dias da autorização da nota.</div>'
      : '<div class="mn-sub">Nenhuma nota pendente de evento conclusivo.</div>';
    const chips = [['todas', `Todas (${it.length})`], ...TIPOS.map(([k, n]) => [k, `${n} (${cont[k] || 0})`]), ['canceladas', `Canceladas (${nCan + nDen})`]];
    if (nErr) chips.push(['erros', `Erros (${nErr})`]);
    $('#mnChips').innerHTML = chips.map(([k, t]) => `<span class="mn-chip${S.filtro === k ? ' on' : ''}" data-f="${k}">${t}</span>`).join('');
    const rows = filtrados();
    $('#mnTabela').innerHTML = `<table><thead><tr><th>Nº</th><th>Emitente</th><th>Emissão</th><th style="text-align:right">Valor (R$)</th><th>Situação</th><th>Manifestação</th><th>Data / prazo</th><th>Chave</th></tr></thead><tbody>${
      rows.map((i) => {
        const st = SIT[i.situacao] || [i.situacao, 'cz'];
        return `<tr><td>${_esc(i.numero || '')}</td><td>${_esc(i.emitente || '')}<span class="mn-mini">${cnpjFmt(i.cnpj_emit)} · ${_esc(i.uf || '')}</span></td><td>${dataBr(i.dh_emissao) || _esc(i.aamm || '')}</td>
          <td style="text-align:right">${i.valor ? brl(i.valor) : '—'}</td><td><span class="mn-st ${st[1]}" title="${_esc(i.motivo || '')}">${st[0]}</span>${['erro', 'nao_encontrada'].includes(i.situacao) ? `<span class="mn-mini">${_esc((i.motivo || '').slice(0, 90))}</span>${(i.tentativas || []).length ? `<span class="mn-mini" title="${_esc(i.tentativas.map((t) => `${t.aut}: ${t.cstat ? t.cstat + ' · ' : ''}${t.motivo}`).join('\n'))}">consultado em: ${_esc(i.tentativas.map((t) => t.aut).join(', '))}</span>` : ''}<a class="mn-link" data-ch="${i.chave}">conferir no Portal da NF-e ↗</a>` : ''}</td>
          <td>${linhaManif(i)}</td><td>${linhaData(i)}</td><td class="mono">${i.chave}</td></tr>`;
      }).join('') || '<tr><td colspan="8" class="mn-sub">Nenhuma nota neste filtro.</td></tr>'}</tbody></table>`;
  }
  $('#mnTabela').addEventListener('click', (ev) => {
    const a = ev.target.closest('.mn-link'); if (!a) return;
    try { navigator.clipboard.writeText(a.dataset.ch); } catch (_) {}
    const url = 'https://www.nfe.fazenda.gov.br/portal/consultaRecaptcha.aspx?tipoConsulta=resumo&tipoConteudo=7PhJ+gAVw2g=';
    if (window.fiscocont.news && window.fiscocont.news.abrirLink) window.fiscocont.news.abrirLink(url); else window.open(url, '_blank');
    toast('Chave copiada: cole no Portal da NF-e para conferir.');
  });
  $('#mnChips').addEventListener('click', (ev) => { const c = ev.target.closest('.mn-chip'); if (c) { S.filtro = c.dataset.f; desenha(); } });
  $('#mnKpis').addEventListener('click', (ev) => { const c = ev.target.closest('.mn-k'); if (c) { S.filtro = c.dataset.f; desenha(); } });

  const nomeArq = () => `Manifestacao_NFe_${(S.res.empresa.nome || '').split(' ').slice(0, 3).join('_')}_${new Date().toISOString().slice(0, 10)}`;
  const titulo = () => `Consulta Manifestação NF-e · ${S.res.empresa.nome} · ${cnpjFmt(S.res.empresa.cnpj)} · ${new Date(S.res.quando).toLocaleString('pt-BR')}`;
  $('#mnXlsx').addEventListener('click', async () => {
    const r = await api.exportar({ formato: 'xlsx', itens: S.res.itens, titulo: titulo(), nome: nomeArq() });
    if (r.error) toast(r.error, true); else if (!r.cancelado) toast('Planilha salva.');
  });
  $('#mnHtml').addEventListener('click', async () => {
    const css = [...document.styleSheets].map((sh) => { try { return [...sh.cssRules].map((x) => x.cssText).filter((t) => /\.mn-|:root/.test(t)).join('\n'); } catch (_) { return ''; } }).join('\n');
    const corpo = `<h2 style="margin:0 0 4px">Consulta Manifestação NF-e</h2><div class="mn-sub" style="margin-bottom:14px">Situação na SEFAZ e manifestação do destinatário · gerado pelo FiscoCont+</div>${$('#mnQry').outerHTML}${$('#mnKpis').outerHTML}<div class="mn-row">${[...document.querySelectorAll('#mnRes .mn-row .mn-c')].map((x) => x.outerHTML).join('')}</div><div class="mn-c">${$('#mnTabela').outerHTML}</div>`;
    const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>${_esc(titulo())}</title><style>:root{--panel:#fff;--line:#e2e8f0;--ink:#0f172a;--ink2:#64748b;--bg:#f4f6fb}body{font-family:Segoe UI,Arial,sans-serif;background:#f4f6fb;color:#0f172a;margin:24px}${css}.mn-tab{max-height:none}.mn-k{cursor:default}</style></head><body>${corpo}</body></html>`;
    const r = await api.exportar({ formato: 'html', html, nome: nomeArq() });
    if (r.error) toast(r.error, true); else if (!r.cancelado) toast('HTML salvo.');
  });

  window._manifEntrar = () => { carregaEmpresas(); if (!S.res) mostraForm(true); };
}

function bindLogin() {
  const form = $('#loginForm');
  if (!form) return;
  const email = $('#loginEmail'), pass = $('#loginPass'), btn = $('#loginBtn'), salvar = $('#loginSalvar');
  try { email.value = localStorage.getItem('fc_ultimo_email') || ''; } catch (_) {}
  // "Salvar meus dados": e-mail e senha ficam no cofre do Windows (a senha nunca vem para a tela)
  let salvo = null;
  const SENHA_FICTICIA = '••••••••••';
  const aplicaSalvo = async () => {
    try { salvo = await window.fiscocont.auth.salvo(); } catch (_) { salvo = null; }
    if (!salvo || !salvo.disponivel) { salvar.closest('label').hidden = true; return; }
    salvar.checked = !!salvo.temSenha;
    if (salvo.temSenha) { email.value = salvo.email; pass.value = SENHA_FICTICIA; pass.dataset.salva = '1'; }
  };
  aplicaSalvo();
  pass.addEventListener('input', () => { if (pass.dataset.salva) { delete pass.dataset.salva; pass.value = pass.value.replace(/•/g, ''); } });
  email.addEventListener('input', () => { if (pass.dataset.salva) { delete pass.dataset.salva; pass.value = ''; } });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    btn.disabled = true; btn.textContent = 'Entrando…';
    const usarSalva = !!pass.dataset.salva;
    const res = await window.fiscocont.login(email.value, usarSalva ? '' : pass.value, { salvar: salvar.checked, usarSalva });
    btn.disabled = false; btn.textContent = 'Entrar';
    if (res && res.ok && salvar.checked) { pass.value = SENHA_FICTICIA; pass.dataset.salva = '1'; }
    else { pass.value = ''; delete pass.dataset.salva; }
    if (res && res.semInternet) { showLicenseBlock({ status: 'semnet', codigo: '' }); }
    if (res && res.ok) _entrou(res);
    else { _loginMsg((res && res.erro) || 'Não foi possível entrar.', !!(res && res.info)); pass.focus(); }
  });
  ['#senhaNova', '#senhaConf'].forEach((id) => $(id).addEventListener('input', _senhaRegras));
  $('#senhaForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!_senhaRegras()) { $('#senhaErr').textContent = 'A senha precisa ter 8 caracteres ou mais, com letras e números, e as duas iguais.'; $('#senhaErr').hidden = false; return; }
    const r = await window.fiscocont.auth.trocarSenha($('#senhaNova').value, salvar.checked);
    if (!r.ok) { $('#senhaErr').textContent = r.erro || 'Não foi possível salvar a senha.'; $('#senhaErr').hidden = false; return; }
    const res = _senhaPendente; _senhaPendente = null;
    res.sessao.trocarSenha = false;
    pass.value = ''; delete pass.dataset.salva;
    toast('Senha criada. Use ela nos próximos acessos.');
    _entrou(res);
  });
  $('#senhaSair').addEventListener('click', async () => { _senhaPendente = null; $('#senhaCard').hidden = true; await window.fiscocont.auth.logout(); _mostraLogin(); });
  $('#lockForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const r = await window.fiscocont.auth.destravar($('#lockPass').value);
    $('#lockPass').value = '';
    if (r.ok) {
      SESSAO.travada = false; SESSAO.ultimoUso = Date.now();
      $('#lockCard').hidden = true; document.querySelector('.login-card').hidden = false;
      $('#loginGate').style.display = 'none';
    } else { $('#lockErr').textContent = r.erro || 'Senha incorreta.'; $('#lockErr').hidden = false; $('#lockPass').focus(); }
  });
  $('#lockSair').addEventListener('click', async () => { await window.fiscocont.auth.logout(); _mostraLogin(); });
  salvar.addEventListener('change', async () => {
    if (!salvar.checked && salvo && salvo.temSenha) {
      await window.fiscocont.auth.esquecerSalvo();
      salvo.temSenha = false;
      if (pass.dataset.salva) { delete pass.dataset.salva; pass.value = ''; }
      toast('Dados de acesso apagados deste computador.');
    }
  });
  const logoutLink = $('#logoutLink');
  if (logoutLink) logoutLink.addEventListener('click', async (e) => {
    e.preventDefault();
    await window.fiscocont.auth.logout();
    _mostraLogin();
    aplicaSalvo();
  });
  window.fiscocont.auth.onMudou((d) => {
    if (d.motivo === 'bloqueado') { _mostraLogin(); _loginMsg('Seu usuário foi bloqueado pelo Admin.'); }
    else if (d.motivo === 'perfil') { if (SESSAO.info) SESSAO.info.perfil = d.perfil; applyRole(d.perfil, d.modulos || null); toast('O Admin mudou os seus acessos.'); }
  });
  _vigiaInatividade();
}

// ------------------------------------------------------------- painel admin: usuários
const PERFIL_NOME = { admin: 'Admin', fiscal: 'Fiscal', contabil: 'Contábil' };
async function loadUsuarios() {
  const box = $('#usrBox');
  box.innerHTML = '<div class="lic-empty">Carregando…</div>';
  const r = await window.fiscocont.usuarios.listar();
  if (r.error) { box.innerHTML = `<div class="lic-warn">Não consegui carregar: ${_esc(r.error)}</div>`; return; }
  USR_LISTA = r.usuarios || [];
  const principal = (u) => (u.email || '').toLowerCase() === 'rafael.max17@gmail.com';
  const sel = (u) => principal(u) || u.voce ? `<span class="usr-fixo">${PERFIL_NOME[u.perfil] || u.perfil}${principal(u) ? ' · principal' : ''}</span>` : `<select class="usr-perfil" data-uid="${_esc(u.uid)}">${Object.entries(PERFIL_NOME).map(([k, v]) => `<option value="${k}" ${u.perfil === k ? 'selected' : ''}>${v}</option>`).join('')}</select>`;
  const qtdMods = (u) => u.perfil === 'admin' ? 'todos' : (u.modulos ? `${u.modulos.length} módulo(s)` : 'padrão do perfil');
  const linhas = USR_LISTA.map((u) => `<tr class="${u.ativo ? '' : 'usr-off'}">
      <td><b>${_esc(u.nome)}</b>${u.voce ? ' <span class="lic-badge ativo">você</span>' : ''}<small>${_esc(u.email)}</small></td>
      <td>${sel(u)}<small>${qtdMods(u)}</small></td>
      <td><span class="lic-badge ${u.ativo ? 'ativo' : 'bloqueado'}">${u.ativo ? 'ativo' : 'bloqueado'}</span>${u.trocarSenha ? '<small>aguardando criar a senha</small>' : ''}</td>
      <td class="lic-actions">
        ${u.perfil === 'admin' ? '' : `<button data-acao="modulos" data-uid="${_esc(u.uid)}">Módulos</button>`}
        ${u.voce || principal(u) ? '' : `<button data-acao="senha" data-uid="${_esc(u.uid)}">Gerar nova senha</button>`}
        ${u.voce || principal(u) ? '' : (u.ativo ? `<button class="off" data-acao="bloquear" data-uid="${_esc(u.uid)}">Bloquear</button>` : `<button class="on" data-acao="ativar" data-uid="${_esc(u.uid)}">Ativar</button>`)}
      </td></tr>`).join('');
  box.innerHTML = `<table class="lic-table usr-table"><thead><tr><th>Usuário</th><th>Perfil / módulos</th><th>Situação</th><th>Ação</th></tr></thead><tbody>${linhas}</tbody></table>`;
  box.querySelectorAll('.usr-perfil').forEach((s2) => s2.addEventListener('change', async () => {
    const x = await window.fiscocont.usuarios.alterar(s2.dataset.uid, { perfil: s2.value, modulos: null });
    if (x.error) { toast(x.error, true); loadUsuarios(); return; }
    toast('Perfil alterado (módulos voltaram ao padrão do perfil). Vale na hora.');
    loadUsuarios();
  }));
  box.querySelectorAll('button[data-acao]').forEach((b) => b.addEventListener('click', async () => {
    const a = b.dataset.acao, u = USR_LISTA.find((x) => x.uid === b.dataset.uid);
    if (a === 'modulos') { usrModulos(u); return; }
    if (a === 'senha') {
      if (!confirm(`Gerar uma nova senha provisória para ${u.nome}? A senha atual dele deixa de funcionar.`)) return;
      b.disabled = true;
      const x = await window.fiscocont.usuarios.novaSenha(u.uid);
      b.disabled = false;
      if (x.error) { toast(x.error, true); return; }
      usrMostraSenha(u.nome, u.email, x.senha, false);
      loadUsuarios();
      return;
    }
    b.disabled = true;
    const x = await window.fiscocont.usuarios.alterar(u.uid, { ativo: a === 'ativar' });
    b.disabled = false;
    if (x.error) { toast(x.error, true); return; }
    toast(a === 'bloquear' ? 'Usuário bloqueado: ele sai do sistema na hora.' : 'Usuário ativado.');
    loadUsuarios();
  }));
}
let USR_LISTA = [];
function usrModal(html) {
  let m = $('#usrModal');
  if (!m) { m = document.createElement('div'); m.id = 'usrModal'; m.className = 'usr-modal'; document.body.appendChild(m); }
  m.innerHTML = `<div class="usr-modal-box">${html}</div>`;
  m.hidden = false;
  m.addEventListener('click', (e) => { if (e.target === m) m.hidden = true; });
  return m;
}
function usrMostraSenha(nome, email, senha, novo) {
  const m = usrModal(`
    <div class="dif-k">${novo ? 'Usuário cadastrado' : 'Nova senha provisória'}</div>
    <h3 style="margin:6px 0 2px">${_esc(nome)}</h3><div class="dif-sub">${_esc(email)}</div>
    <div class="usr-senha"><code id="usrSenhaTxt">${_esc(senha)}</code><button class="act inv-export" id="usrCopiar">Copiar</button></div>
    <div class="dif-sub">Passe esta senha para a pessoa. No primeiro acesso o sistema pede para ela criar a própria senha (8 caracteres ou mais, com letras e números).
      Esta senha não aparece de novo: se perder, gere outra.</div>
    <div class="dif-acts"><button class="act inv-export" id="usrOkSenha" style="background:var(--accent);color:#fff;border-color:transparent">Pronto</button></div>`);
  $('#usrCopiar').addEventListener('click', () => {
    navigator.clipboard.writeText(`Usuário: ${email}\nSenha provisória: ${senha}`).then(() => toast('Copiado: e-mail e senha provisória.'));
  });
  $('#usrOkSenha').addEventListener('click', () => { m.hidden = true; });
}
function usrModulos(u) {
  const cat = catalogoModulos().filter((x) => !['admin-usuarios', 'admin-lic'].includes(x.view));
  const marcados = new Set(u.modulos || modulosPadrao(u.perfil));
  const grupos = [...new Set(cat.map((x) => x.grupoNome))];
  const m = usrModal(`
    <div class="dif-k">Módulos liberados</div>
    <h3 style="margin:6px 0 2px">${_esc(u.nome)}</h3><div class="dif-sub">Perfil ${PERFIL_NOME[u.perfil] || u.perfil} · marque o que ${_esc(u.nome.split(' ')[0])} pode ver. Usuários e Licenças são só do Admin.</div>
    <div class="usr-mods">${grupos.map((g) => `<div class="usr-mod-g"><b>${_esc(g)}</b>
      ${cat.filter((x) => x.grupoNome === g).map((x) => `<label><input type="checkbox" value="${_esc(x.view)}" ${marcados.has(x.view) ? 'checked' : ''}> ${_esc(x.nome)}</label>`).join('')}</div>`).join('')}</div>
    <div class="dif-acts" style="justify-content:space-between">
      <button class="act inv-export" id="usrModPadrao">Voltar ao padrão do perfil</button>
      <span><button class="act inv-export" id="usrModCancelar">Cancelar</button>
      <button class="act inv-export" id="usrModSalvar" style="background:var(--accent);color:#fff;border-color:transparent">Salvar</button></span>
    </div>`);
  $('#usrModCancelar').addEventListener('click', () => { m.hidden = true; });
  $('#usrModPadrao').addEventListener('click', async () => {
    const x = await window.fiscocont.usuarios.alterar(u.uid, { modulos: null });
    if (x.error) { toast(x.error, true); return; }
    m.hidden = true; toast('Módulos de volta ao padrão do perfil.'); loadUsuarios();
  });
  $('#usrModSalvar').addEventListener('click', async () => {
    const lista = [...m.querySelectorAll('.usr-mods input:checked')].map((i) => i.value);
    const x = await window.fiscocont.usuarios.alterar(u.uid, { modulos: lista });
    if (x.error) { toast(x.error, true); return; }
    m.hidden = true; toast(`Módulos salvos (${lista.length}). Vale na hora, mesmo com o sistema aberto.`); loadUsuarios();
  });
}
function bindUsuarios() {
  const b = $('#btnUsrCadastrar');
  if (!b) return;
  $('#btnUsrRefresh').addEventListener('click', loadUsuarios);
  b.addEventListener('click', async () => {
    b.disabled = true;
    const r = await window.fiscocont.usuarios.cadastrar({ nome: $('#usrNome').value, email: $('#usrEmail').value, perfil: $('#usrPerfil').value });
    b.disabled = false;
    if (r.error) { toast(r.error, true); return; }
    usrMostraSenha(r.nome, r.email, r.senha, true);
    $('#usrNome').value = ''; $('#usrEmail').value = '';
    loadUsuarios();
  });
}

// ------------------------------------------------------------- novidades da versão
// Busca (via main process) o texto da release atual no GitHub — o mesmo
// texto escrito na hora de publicar cada versão — e mostra num modal só
// quando a versão mudou desde a última vez que a pessoa viu.
// Seções "## Admin ..." são privativas do Admin: para os demais perfis, somem
// das Novidades (rede de proteção; as notas já são escritas sem elas).
function _notasParaHtml(notas) {
  const linhas = notas.split('\n').map((l) => l.trim()).filter(Boolean);
  let html = '', aberta = false, pula = false;
  const fecha = () => { if (aberta) { html += '</ul>'; aberta = false; } };
  for (const l of linhas) {
    if (/^#\s/.test(l)) continue;                       // título "# FiscoCont+ x.y.z" (já está no cabeçalho do modal)
    if (/^#{2,}\s/.test(l)) {
      const tit = l.replace(/^#+\s*/, '');
      pula = ROLE !== 'admin' && /\badmin\b/i.test(tit);
      fecha();
      if (!pula) html += `<div style="font-weight:600;margin:10px 0 6px">${_esc(tit)}</div>`;
      continue;
    }
    if (pula) continue;
    if (!aberta) { html += '<ul style="margin:0;padding-left:20px">'; aberta = true; }
    html += `<li style="margin-bottom:8px">${_esc(l.replace(/^[-*]\s*/, '').replace(/\*\*/g, ''))}</li>`;
  }
  fecha();
  return html;
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
  const lk = $('#lockCard'); if (lk) lk.hidden = true;            // o bloqueio da licença tem prioridade; a trava volta depois
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
  } else if (res.status === 'semnet') {
    if (title) title.textContent = 'Sem internet';
    if (sub) sub.textContent = 'Por segurança, o FiscoCont+ só abre com o computador conectado à internet.';
    if (hint) hint.textContent = 'Conecte o computador e clique em Verificar novamente.';
    if (codeEl) codeEl.textContent = 'OFFLINE';
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
  if (SESSAO.travada && ROLE) { _mostraTrava(); return; }   // travado por inatividade: continua pedindo a senha
  if (loginCard) loginCard.hidden = false;
  // Achado real: essa função nunca escondia o #loginGate, só trocava qual
  // card aparecia dentro dele — então depois de bloquear e reativar, o app
  // ficava preso pedindo senha de novo mesmo já reativado. Se já havia uma
  // sessão ativa (ROLE definido) quando a liberação chegou, o usuário só
  // estava interrompido, não deslogado — some com o gate inteiro e devolve
  // ele pra tela onde estava, sem pedir senha de novo.
  if (gate && ROLE) gate.style.display = 'none';
}
async function checkLicenseGate(inicial) {
  if (!window.fiscocont.license) return true;
  // por segurança o sistema só abre com internet (licença, login e bloqueio em tempo real dependem dela)
  if (inicial !== false && window.fiscocont.auth && window.fiscocont.auth.conectado) {
    let net = { ok: true };
    try { net = await window.fiscocont.auth.conectado(); } catch (_) { net = { ok: false }; }
    if (!net.ok) { showLicenseBlock({ status: 'semnet', codigo: '' }); return false; }
  }
  let res;
  try { res = await window.fiscocont.license.check(); } catch (_) { res = { status: 'offline', codigo: '' }; }
  if (!res || res.configurado === false || res.status === 'ativo') {
    hideLicenseBlock();
    return true;
  }
  // com o sistema já em uso, uma queda rápida de internet não derruba a tela: só bloqueio/pendência do Admin
  if (inicial === false && ROLE && res.status === 'offline') return true;
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
    if (warnBox) warnBox.innerHTML = `<div class="lic-warn">Não consegui carregar: ${_esc(res.error)}</div>`;
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
      <td>${it.versao ? 'v' + _esc(it.versao) : '—'}<br><span style="color:var(--ink2);font-size:11px">${_esc(it.usuario || '')}</span></td>
      <td>${fmtDt(it.primeiroAcesso)}</td>
      <td>${fmtDt(it.ultimoAcesso)}</td>
      <td class="lic-actions">
        <button class="on" data-code="${_esc(it.codigo)}" data-status="ativo">Ativar</button>
        <button class="off" data-code="${_esc(it.codigo)}" data-status="bloqueado">Bloquear</button>
      </td>
    </tr>`;
  }
  box.innerHTML = `<table class="lic-table"><thead><tr><th>Código</th><th>Computador</th><th>Status</th><th>Versão / usuário</th><th>1º acesso</th><th>Último acesso</th><th>Ação</th></tr></thead><tbody>${rows}</tbody></table>`;
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
  // estado da conferência: o SPED escolhido + (opcional) os relatórios do Domínio; qualquer
  // mudança relê tudo e redesenha o painel
  const est = { sped: null, entradas: null, saidas: null, html: null, empresa: '' };
  const nome = (p) => p.split(/[\\/]/).pop();
  async function rodar() {
    overlay(true, (est.entradas || est.saidas) ? 'Lendo a EFD-Contribuições e conferindo com o Domínio…' : 'Lendo a EFD-Contribuições…');
    const res = await window.fiscocont.fiscal.efdContrib(est.sped, { entradas: est.entradas, saidas: est.saidas });
    overlay(false);
    if (res.error) { toast(res.error, true); return false; }
    $('#efdVazio').hidden = true;
    const frame = $('#efdFrame');
    frame.hidden = false;
    frame.srcdoc = res.painelHtml;
    est.html = res.painelHtml;
    est.dados = res.resumo;            // para avisar do saldo credor antes de gerar o relatório do cliente
    est.empresa = res.resumo?.empresa?.nome || '';
    $('#btnEfdExportar').disabled = false;
    $('#btnEfdDomSaidas').disabled = false;
    $('#btnEfdDomEntradas').disabled = false;
    $('#btnEclAbrir').disabled = false;
    rlAlerta(res.resumo && res.resumo.reducao_linear, est.rlVisto !== est.sped);
    est.rlVisto = est.sped;
    return true;
  }
  // ---- alerta da redução linear (LC 224/2025) ao importar o arquivo ----
  const brlR = (v) => (Number(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pctR = (v) => String(Number(v) || 0).replace('.', ',') + '%';
  function rlIrParaConferencia() {
    try {
      const doc = $('#efdFrame').contentDocument;
      const alvo = doc && doc.querySelector('.rl-aviso');
      if (alvo) alvo.scrollIntoView({ behavior: 'smooth', block: 'start' });
      $('#efdFrame').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (_) {}
  }
  function rlAlerta(rl, abrirJanela) {
    const ban = $('#efdRlBanner');
    if (!rl) { ban.hidden = true; return; }
    const comp = rl.competencia ? `${rl.competencia.slice(5)}/${rl.competencia.slice(0, 4)}` : '';
    const cfg = {
      falta: { cls: 'err', t: `Redução linear não informada · faltam R$ ${brlR(rl.ap_total)} de PIS/COFINS`,
               s: `${rl.notas} nota(s) com alíquota zero que entram na redução (LC 224/2025) sem ajuste no M220/M620 · risco de multa de 75% + Selic` },
      menor: { cls: 'warn', t: `Redução linear informada a menor · faltam R$ ${brlR(rl.diferenca)} de PIS/COFINS`,
               s: `Declarado R$ ${brlR(rl.de_total)} · apurado pelo sistema R$ ${brlR(rl.ap_total)}` },
      maior: { cls: 'warn', t: `Redução linear informada a maior · R$ ${brlR(-rl.diferenca)} acima do devido`,
               s: `Declarado R$ ${brlR(rl.de_total)} · apurado pelo sistema R$ ${brlR(rl.ap_total)} — pode haver produto fora da redução (cesta básica, hortifruti, ZFM) no ajuste` },
      ok: { cls: 'ok', t: 'Redução linear conferida ✓', s: `Ajuste de R$ ${brlR(rl.de_total)} de acordo com o apurado pelo sistema` },
    }[rl.status];
    if (!cfg) { ban.hidden = true; return; }
    ban.className = 'rl-ban ' + cfg.cls;
    ban.innerHTML = `<div class="rl-ban-ic">${cfg.cls === 'ok' ? '✓' : '⚠️'}</div><div class="rl-ban-tx"><b>${_esc(cfg.t)}</b><small>${_esc(cfg.s)}</small></div>`
      + (cfg.cls === 'ok' ? '' : '<button class="act inv-export rl-ban-bt">Ver detalhes</button>');
    ban.hidden = false;
    const bt = ban.querySelector('.rl-ban-bt');
    if (bt) bt.onclick = () => rlJanela(rl, cfg, comp);
    if (abrirJanela && cfg.cls !== 'ok') rlJanela(rl, cfg, comp);
  }
  function rlJanela(rl, cfg, comp) {
    let m = $('#efdRlModal');
    if (!m) { m = document.createElement('div'); m.id = 'efdRlModal'; m.className = 'rl-modal'; document.body.appendChild(m); }
    const titulo = { falta: 'Redução linear não informada nesta EFD-Contribuições', menor: 'Redução linear informada a menor', maior: 'Redução linear informada a maior' }[rl.status];
    const intro = rl.status === 'falta'
      ? `O arquivo tem <b>R$ ${brlR(rl.receita)}</b> de vendas com alíquota zero (CST 06) em <b>${rl.notas} nota(s)</b> de <b>${rl.produtos} produto(s)</b> que entram na redução, mas <b>não há ajuste no M220/M620 (código 11)</b>.`
      : rl.status === 'menor'
        ? `O ajuste declarado (R$ ${brlR(rl.de_total)}) é <b>menor</b> que o apurado pelo sistema para as vendas com alíquota zero que entram na redução (R$ ${brlR(rl.receita)} em ${rl.notas} nota(s)).`
        : `O ajuste declarado (R$ ${brlR(rl.de_total)}) é <b>maior</b> que o apurado pelo sistema. Confira se há produto que não entra na redução (cesta básica, hortifruti, vendas para ZFM/ALC) no M225/M625.`;
    const v3 = rl.status === 'falta'
      ? [['PIS a acrescentar (' + pctR(rl.r_pis) + ')', rl.ap_pis], ['COFINS a acrescentar (' + pctR(rl.r_cof) + ')', rl.ap_cofins], ['Total que deixou de ser apurado', rl.ap_total]]
      : [['Apurado pelo sistema', rl.ap_total], ['Declarado no arquivo', rl.de_total], [rl.status === 'menor' ? 'Faltam' : 'A maior', Math.abs(rl.diferenca)]];
    const riscos = rl.status === 'maior'
      ? `<div><b>PIS/COFINS pago a mais</b> no mês: a diferença pode ser recuperada retificando a EFD e a DCTFWeb</div><div><b>Crédito indevido do cliente</b> fica de fora: vale conferir a lista de produtos</div>`
      : `<div><b>Multa de ofício de 75%</b> sobre a diferença, se a Receita apurar primeiro (Lei 9.430/1996, art. 44, I)</div><div><b>Juros Selic</b> desde o vencimento do PIS/COFINS do mês</div>
         <div><b>EFD × DCTFWeb divergentes:</b> o débito declarado fica menor que o devido</div><div>Pagando antes da fiscalização: só <b>multa de mora de 0,33% ao dia, limitada a 20%</b> (Lei 9.430/1996, art. 61)</div>`;
    const passos = rl.status === 'maior'
      ? '<li>Conferir na lista de produtos quais não entram na redução</li><li>Corrigir o M220/M620 e o M225/M625</li><li>Retificar a EFD-Contribuições e a DCTFWeb do mês</li>'
      : '<li>Lançar o ajuste no M220/M620 (código 11) e o detalhamento por nota no M225/M625</li><li>Retificar a EFD-Contribuições e a DCTFWeb do mês</li><li>Recolher a diferença de PIS/COFINS com os acréscimos</li>';
    m.innerHTML = `<div class="rl-box ${cfg.cls}"><div class="rl-hd"><div class="rl-bi">⚠️</div><div><h2>${titulo}</h2><small>${_esc(rl.empresa)} · ${comp} · LC 224/2025 em vigor desde 01/04/2026</small></div></div>
      <div class="rl-bd"><div class="rl-intro">${intro}</div>
      <div class="rl-vals">${v3.map(([t, v]) => `<div><small>${t}</small><b>R$ ${brlR(v)}</b></div>`).join('')}</div>
      <div class="rl-sec">${rl.status === 'maior' ? 'O QUE ISSO SIGNIFICA' : 'RISCOS SE NÃO CORRIGIR'}</div><div class="rl-risk">${riscos}</div>
      <div class="rl-sec">O QUE FAZER</div><ol class="rl-passos">${passos}</ol></div>
      <div class="rl-ft"><button class="act inv-export" id="rlVer">Ver produtos e notas</button><button class="act inv-export rl-prim" id="rlOk">Entendi</button></div></div>`;
    m.hidden = false;
    $('#rlOk').onclick = () => { m.hidden = true; };
    $('#rlVer').onclick = () => { m.hidden = true; rlIrParaConferencia(); };
    m.onclick = (ev) => { if (ev.target === m) m.hidden = true; };
  }
  btn.addEventListener('click', async () => {
    const pick = await window.fiscocont.fiscal.pickEfdContrib();
    if (pick.canceled) return;
    est.sped = pick.path; est.entradas = null; est.saidas = null;
    $('#efdArquivoNome').textContent = nome(pick.path);
    $('#efdDomSaidasNome').textContent = '';
    $('#efdDomEntradasNome').textContent = '';
    await rodar();
  });
  async function anexarDominio(tipo) {   // 'saidas' | 'entradas'
    const pick = await window.fiscocont.fiscal.pickDominioPdf(tipo === 'saidas' ? 'Saídas' : 'Entradas');
    if (pick.canceled) return;
    const anterior = est[tipo];
    est[tipo] = pick.path;
    if (await rodar()) $(tipo === 'saidas' ? '#efdDomSaidasNome' : '#efdDomEntradasNome').textContent = nome(pick.path);
    else est[tipo] = anterior;
  }
  $('#btnEfdDomSaidas').addEventListener('click', () => anexarDominio('saidas'));
  $('#btnEfdDomEntradas').addEventListener('click', () => anexarDominio('entradas'));
  // ---- relatório para o cliente ----
  const ecl = { html: null, estatico: null, anterior: null, resumo: null };
  const nomeCliente = () => `Relatorio-Cliente_${(ecl.resumo?.empresa || 'empresa').replace(/\s+/g, '_')}_${(ecl.resumo?.competencia || '').replace('/', '-')}`;
  // saldo credor: o valor sai direto do arquivo e o Domínio já gerou esse saldo errado — o escritório confere antes de gerar
  function saldoCredorDoArquivo() {
    const pis = (est.dados && est.dados.saldo_credor_pis) || 0;
    const cofins = (est.dados && est.dados.saldo_credor_cofins) || 0;
    return { pis, cofins, total: pis + cofins };
  }
  const brl = (v) => v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function atualizarAvisoSaldo() {
    const s = saldoCredorDoArquivo();
    const tem = s.total > 0.005;
    $('#eclSaldoAviso').hidden = !tem;
    if (tem) $('#eclSaldoTexto').textContent = `PIS: R$ ${brl(s.pis)} · COFINS: R$ ${brl(s.cofins)}.`;
    $('#eclSaldoOk').checked = false;
    $('#btnEclGerar').disabled = tem;          // com saldo credor, só gera depois da conferência
  }
  $('#eclSaldoOk').addEventListener('change', () => { $('#btnEclGerar').disabled = !$('#eclSaldoOk').checked; });
  $('#btnEclAbrir').addEventListener('click', () => { atualizarAvisoSaldo(); $('#eclModal').hidden = false; });
  $('#btnEclFechar').addEventListener('click', () => { $('#eclModal').hidden = true; });
  $('#btnEclAnterior').addEventListener('click', async () => {
    const pick = await window.fiscocont.fiscal.pickEfdContrib();
    if (pick.canceled) return;
    ecl.anterior = pick.path;
    $('#eclAnteriorNome').textContent = nome(pick.path);
    $('#btnEclLimparAnterior').hidden = false;
  });
  $('#btnEclLimparAnterior').addEventListener('click', () => { ecl.anterior = null; $('#eclAnteriorNome').textContent = ''; $('#btnEclLimparAnterior').hidden = true; });
  $('#btnEclGerar').addEventListener('click', async () => {
    if (!est.sped) return;
    const opcoes = { recado: $('#eclRecado').value, vencimento: $('#eclVenc').value, creditos: $('#eclCreditos').checked, tecnico: $('#eclTecnico').checked };
    $('#eclModal').hidden = true;
    overlay(true, 'Gerando o relatório do cliente…');
    const res = await window.fiscocont.fiscal.efdCliente({ spedPath: est.sped, anteriorPath: ecl.anterior, opcoes });
    overlay(false);
    if (res.error) { toast(res.error, true); return; }
    ecl.html = res.html; ecl.estatico = res.htmlEstatico; ecl.resumo = res.resumo;
    $('#efdFrame').srcdoc = res.html;
    $('#btnEclHtml').hidden = false; $('#btnEclPdf').hidden = false; $('#btnEclVoltar').hidden = false;
    toast((res.avisos && res.avisos.length) ? res.avisos.join(' ') : 'Relatório do cliente gerado.', !!(res.avisos && res.avisos.length));
  });
  $('#btnEclVoltar').addEventListener('click', () => {
    if (est.html) $('#efdFrame').srcdoc = est.html;
    $('#btnEclVoltar').hidden = true;
  });
  $('#btnEclHtml').addEventListener('click', async () => {
    if (!ecl.html) return;
    const r = await window.fiscocont.fiscal.efdClienteSalvar({ html: ecl.html, nomeSugerido: nomeCliente() });
    if (r.canceled) return;
    if (r.error) { toast(r.error, true); return; }
    toast('Relatório do cliente salvo (HTML).');
    window.fiscocont.abrirArquivo(r.path);
  });
  $('#btnEclPdf').addEventListener('click', async () => {
    if (!ecl.estatico) return;
    overlay(true, 'Gerando o PDF…');
    const r = await window.fiscocont.fiscal.efdClientePdf({ htmlEstatico: ecl.estatico, nomeSugerido: nomeCliente() });
    overlay(false);
    if (r.canceled) return;
    if (r.error) { toast(r.error, true); return; }
    toast('Relatório do cliente salvo (PDF).');
    window.fiscocont.abrirArquivo(r.path);
  });
  $('#btnEfdExportar').addEventListener('click', async () => {
    if (!est.html) return;
    const res = await window.fiscocont.fiscal.nfseExportarHtml(est.html, 'efd-contrib', est.empresa);
    if (res.canceled) return;
    if (res.error) { toast(res.error, true); return; }
    toast('Conferência exportada.');
    window.fiscocont.openPath(res.path);
  });
}

function bindCorrigirEfd() {
  const btnPick = $('#btnCorrEfdPick');
  if (!btnPick) return;
  const est = { sped: null, pva: null, html: null, corrigido: null, empresa: '' };
  const nome = (p) => p.split(/[\\/]/).pop();
  btnPick.addEventListener('click', async () => {
    const pick = await window.fiscocont.fiscal.pickEfdContrib();
    if (pick.canceled) return;
    est.sped = pick.path; est.html = null; est.corrigido = null;
    est.pva = null;                       // o PDF do PVA é de uma empresa/período: ao trocar o SPED, escolhe de novo
    $('#corrEfdPvaNome').textContent = '';
    $('#corrEfdNome').textContent = nome(pick.path);
    $('#btnCorrEfdRodar').disabled = false;
    $('#btnCorrEfdMono').disabled = false;
    $('#corrEfdMono').hidden = true;
    $('#btnCorrEfdBaixar').disabled = true;
    $('#btnCorrEfdHtml').disabled = true;
  });
  $('#btnCorrEfdPva').addEventListener('click', async () => {
    const pick = await window.fiscocont.fiscal.pickPvaPdf();
    if (pick.canceled) return;
    est.pva = pick.path;
    $('#corrEfdPvaNome').textContent = nome(pick.path);
  });
  $('#btnCorrEfdRodar').addEventListener('click', async () => {
    if (!est.sped) return;
    overlay(true, 'Corrigindo a EFD-Contribuições…');
    const res = await window.fiscocont.fiscal.efdCorrigir(est.sped, est.pva, ($('#corrEfdConta')?.value || '').trim());
    overlay(false);
    if (res.error) { toast(res.error, true); return; }
    $('#corrEfdVazio').hidden = true;
    const frame = $('#corrEfdFrame');
    frame.hidden = false;
    frame.srcdoc = res.painelHtml;
    est.html = res.painelHtml;
    est.corrigido = res.corrigidoPath;
    est.empresa = res.resumo?.empresa?.nome || '';
    $('#btnCorrEfdBaixar').disabled = false;
    $('#btnCorrEfdHtml').disabled = false;
    const pend = res.resumo?.pendencias || 0;
    toast(pend ? `Correção concluída — ${pend} pendência(s) para a sua decisão.` : 'Correção concluída.');
  });
  $('#btnCorrEfdBaixar').addEventListener('click', async () => {
    const r = await window.fiscocont.fiscal.efdCorrigirSalvar(est.corrigido, nome(est.sped));
    if (r.canceled) return;
    if (r.error) { toast(r.error, true); return; }
    toast('SPED corrigido salvo.');
  });
  // ---------- ⚡ Corrigir monofásico (pedido do Rafael, 15/10) ----------
  const MONO = { an: null, sel: new Set() };
  const fm = (v) => (Number(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const dt = (s) => (s && s.length === 8 ? `${s.slice(0, 2)}/${s.slice(2, 4)}/${s.slice(4)}` : s || '');
  const conta = (root) => root.querySelectorAll('[data-n]').forEach((el) => {
    const alvo = Number(el.dataset.n) || 0, brl = el.dataset.fmt === 'brl', t0 = performance.now();
    const f = (v) => (brl ? 'R$ ' + fm(v) : Math.round(v).toLocaleString('pt-BR'));
    const passo = (t) => { const k = Math.min(1, (t - t0) / 900); el.textContent = f(alvo * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(passo); };
    requestAnimationFrame(passo);
  });
  function monoPrev() {
    const an = MONO.an, gs = (an.grupos || []).filter((g) => MONO.sel.has(g.grupo));
    const vp = gs.reduce((t, g) => t + g.pis, 0), vc = gs.reduce((t, g) => t + g.cofins, 0);
    const a = an.apuracao_antes || {}, ap = (a.PIS || {}).total || 0, ac = (a.COFINS || {}).total || 0;
    const linha = (rot, antes, depois, forte) => `<tr><td>${rot}</td><td class="n">R$ ${fm(antes)}</td><td class="n"><b style="color:${forte ? '#0b7a55' : 'inherit'}">R$ ${fm(depois)}</b></td></tr>`;
    $('#monoPrev').innerHTML = `<table class="dif-mini"><thead><tr><th></th><th class="n">Antes</th><th class="n">Depois</th></tr></thead><tbody>
      ${linha('PIS a recolher (M200)', ap, Math.max(0, ap - vp), true)}
      ${linha('COFINS a recolher (M600)', ac, Math.max(0, ac - vc), true)}
      <tr><td><b>Economia no mês</b></td><td></td><td class="n"><b style="color:#0b7a55;font-size:17px">R$ ${fm(vp + vc)}</b></td></tr></tbody></table>`;
    $('#btnMonoAplicar').disabled = !gs.length || !$('#monoRevenda').checked;
  }
  function monoRender() {
    const an = MONO.an, emp = an.empresa || {}, k = an.kpi || {}, box = $('#corrEfdMono');
    const grupos = an.grupos || [];
    const maxV = Math.max(1, ...grupos.map((g) => g.pis + g.cofins));
    box.innerHTML = `
      <div class="dif-head"><div>
        <div class="dif-k">Correção da EFD-Contribuições · Admin · PIS/COFINS monofásico na revenda</div>
        <h3>${esc(emp.nome || '')}</h3>
        <div class="dif-sub">CNPJ ${esc(emp.cnpj || '')} · período ${dt(emp.ini)} a ${dt(emp.fim)} · arquivo <b>${est.corrigido ? 'já corrigido nesta sessão' : 'original'}</b></div>
      </div><div><button class="act inv-export" id="btnMonoFechar">Fechar</button></div></div>
      <div class="dif-lei"><b>Regra:</b> nos produtos de incidência monofásica o PIS/COFINS é cobrado de uma vez na indústria, refinaria ou importador.
        Na <b>revenda</b> a alíquota é zero — CST <b>04</b>. Item com NCM monofásico vendido com CST <b>01</b> paga PIS/COFINS de novo.
        Fontes: Lei 9.718/1998, arts. 4º e 5º (combustíveis e álcool); Lei 10.147/2000, arts. 1º e 2º (farmacêuticos e perfumaria); Lei 10.485/2002 (pneus); Tabela 4.3.10 da EFD-Contribuições.</div>
      <div class="dif-kpis">
        <div><span>Itens de venda</span><b data-n="${k.itens_venda || 0}">0</b><small>no arquivo do mês</small></div>
        <div><span>Com produto monofásico</span><b data-n="${k.itens_mono || 0}">0</b><small>pelo NCM ou CFOP de combustível</small></div>
        <div class="k-err"><span>Tributados indevidamente</span><b data-n="${k.indevidos || 0}">0</b><small>CST 01 na revenda</small></div>
        <div class="k-warn"><span>PIS + COFINS a mais</span><b data-n="${(k.pis || 0) + (k.cofins || 0)}" data-fmt="brl">R$ 0,00</b><small>PIS R$ ${fm(k.pis)} · COFINS R$ ${fm(k.cofins)}</small></div>
        <div class="k-ok"><span>Já corretos</span><b data-n="${k.corretos || 0}">0</b><small>sem tributo (CST 04/06)</small></div>
      </div>
      ${(an.pendencias || []).map((p) => `<div class="dif-av"><b>${esc(p.titulo)}</b><br>${esc(p.detalhe)}</div>`).join('')}
      ${grupos.length ? `
      <div class="mono-grid">
        <div class="mono-card">
          <div class="dif-k">Itens tributados que são monofásicos — marque o que corrigir</div>
          ${grupos.map((g, i) => `
            <label class="mono-g" style="--i:${i}">
              <input type="checkbox" class="mono-ck" data-g="${esc(g.grupo)}" ${MONO.sel.has(g.grupo) ? 'checked' : ''}>
              <div class="mono-gt"><b>${esc(g.grupo)}</b><small>${g.itens} item(ns) · receita R$ ${fm(g.receita)} · natureza ${esc(g.nat_rec)} — ${esc(g.nat_desc)} · ${esc(g.lei)}</small>
                <span class="mono-bar"><i style="--w:${((g.pis + g.cofins) / maxV * 100).toFixed(1)}%"></i></span></div>
              <div class="mono-gv">R$ ${fm(g.pis + g.cofins)}<small>PIS ${fm(g.pis)} · COFINS ${fm(g.cofins)}</small></div>
            </label>
            <details class="mono-ex"><summary>ver exemplos</summary><table class="dif-tab"><thead><tr><th>Nota</th><th>Produto</th><th>NCM</th><th>CFOP</th><th>CST</th><th class="n">Receita</th><th class="n">PIS+COFINS</th></tr></thead>
              <tbody>${(g.exemplos || []).map((e) => `<tr><td>${esc(e.nota)}</td><td>${esc(e.produto)}</td><td>${esc(e.ncm)}</td><td>${esc(e.cfop)}</td><td><span class="dif-b b-err">${esc(e.cst)} → 04</span></td><td class="n">R$ ${fm(e.receita)}</td><td class="n">R$ ${fm(e.valor)}</td></tr>`).join('')}</tbody></table></details>`).join('')}
          ${(an.fora || []).length ? `<div class="dif-av" style="margin-top:12px"><b>Fora da correção automática (conferir à mão)</b><ul>${an.fora.map((f) => `<li>${esc(f.grupo)} — ${f.itens} item(ns), R$ ${fm(f.valor)}: ${esc(f.motivo)}</li>`).join('')}</ul></div>` : ''}
        </div>
        <div class="mono-card">
          <div class="dif-k">Apuração antes × depois do que está marcado</div>
          <div id="monoPrev"></div>
          <div class="dif-sub" style="margin-top:10px"><b>O que o arquivo novo muda:</b> CST 01 → 04 nos itens (C170, C175 de combustível, C181/C185), zera base, alíquota e valor,
            ajusta o VL_PIS/VL_COFINS do C100, refaz M210/M610, M200/M600 e M205/M605, informa a receita a alíquota zero no M400/M410 e M800/M810 e recalcula os contadores. O original nunca é alterado.</div>
          <label class="mono-conf"><input type="checkbox" id="monoRevenda"><span>Confirmo que a empresa <b>revende</b> esses produtos (não é fabricante nem importadora).</span></label>
          <div class="dif-acts"><button class="act inv-export" id="btnMonoAplicar" disabled style="background:#0ea472;color:#fff;border-color:transparent">⚡ Aplicar e gerar EFD corrigida</button></div>
          <div class="dif-av ok" style="margin-top:12px"><b>Meses anteriores:</b> o mesmo erro em meses já transmitidos vira crédito a recuperar (retificação + PER/DCOMP, até 5 anos). A <b>Recuperação Tributária</b> calcula esse valor.</div>
        </div>
      </div>` : `<div class="dif-av ok">Nenhum item de revenda com produto monofásico tributado neste arquivo. ${k.itens_mono ? `${k.itens_mono} item(ns) monofásico(s) já estão sem tributo.` : ''}</div>`}`;
    box.hidden = false;
    conta(box);
    box.querySelectorAll('.mono-ck').forEach((c) => c.addEventListener('change', () => { c.checked ? MONO.sel.add(c.dataset.g) : MONO.sel.delete(c.dataset.g); monoPrev(); }));
    $('#btnMonoFechar').addEventListener('click', () => { box.hidden = true; });
    if (grupos.length) {
      $('#monoRevenda').addEventListener('change', monoPrev);
      monoPrev();
      $('#btnMonoAplicar').addEventListener('click', async () => {
        overlay(true, 'Corrigindo o monofásico na EFD-Contribuições…');
        const r = await window.fiscocont.admin.monoAplicar({ efdPath: est.corrigido || est.sped, grupos: [...MONO.sel] });
        overlay(false);
        if (r.error) { toast(r.error, true); return; }
        est.corrigido = r.corrigidoPath;
        $('#btnCorrEfdBaixar').disabled = false;
        const x = r.res || {};
        box.innerHTML = `<div class="dif-head"><div><div class="dif-k">Monofásico corrigido</div><h3>${esc(emp.nome || '')}</h3></div>
          <div><button class="act inv-export" id="btnMonoFechar2">Fechar</button></div></div>
          <div class="dif-kpis">
            <div class="k-ok"><span>Itens corrigidos</span><b data-n="${x.itens_corrigidos || 0}">0</b><small>CST 01 → 04</small></div>
            <div class="k-ok"><span>Economia no mês</span><b data-n="${(x.pis || 0) + (x.cofins || 0)}" data-fmt="brl">R$ 0,00</b><small>PIS R$ ${fm(x.pis)} · COFINS R$ ${fm(x.cofins)}</small></div>
            <div><span>PIS a recolher agora</span><b data-n="${((x.apuracao_depois || {}).PIS || {}).total || 0}" data-fmt="brl">R$ 0,00</b><small>M200</small></div>
            <div><span>COFINS a recolher agora</span><b data-n="${((x.apuracao_depois || {}).COFINS || {}).total || 0}" data-fmt="brl">R$ 0,00</b><small>M600</small></div>
          </div>
          ${(x.pendencias || []).map((p) => `<div class="dif-av"><b>${esc(p.titulo)}</b><br>${esc(p.detalhe)}</div>`).join('')}
          <div class="dif-av ok">Arquivo novo pronto. Use <b>Baixar SPED corrigido</b> para salvar e valide no PVA. Se rodar o <b>Corrigir</b> depois, ele parte do arquivo original — rode o Corrigir antes do monofásico.</div>`;
        conta(box);
        $('#btnMonoFechar2').addEventListener('click', () => { box.hidden = true; });
        toast('Monofásico corrigido — baixe o SPED corrigido.');
      });
    }
  }
  $('#btnCorrEfdMono').addEventListener('click', async () => {
    if (!est.sped) return;
    overlay(true, 'Procurando produtos monofásicos tributados…');
    const r = await window.fiscocont.admin.monoAnalisar({ efdPath: est.corrigido || est.sped });
    overlay(false);
    if (r.error) { toast(r.error, true); return; }
    MONO.an = r.res;
    MONO.sel = new Set((r.res.grupos || []).map((g) => g.grupo));
    monoRender();
    $('#corrEfdMono').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  $('#btnCorrEfdHtml').addEventListener('click', async () => {
    if (!est.html) return;
    const r = await window.fiscocont.fiscal.nfseExportarHtml(est.html, 'efd-corrigir', est.empresa);
    if (r.canceled) return;
    if (r.error) { toast(r.error, true); return; }
    toast('Relatório exportado.');
    window.fiscocont.openPath(r.path);
  });
}

// ---------- ⚡ Automatizar correção — SPED Fiscal de todos os clientes do mês (pedido do Rafael, 15/10) ----------
function bindLoteSped() {
  const btn = $('#btnCorrLote');
  if (!btn) return;
  const L = { pasta: null, pastaXmls: null, an: null, esc: {}, usar: {}, res: null };
  const fm = (v) => (Number(v) || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const dt = (s) => (s && s.length === 8 ? `${s.slice(0, 2)}/${s.slice(2, 4)}/${s.slice(4)}` : s || '');
  const cnpjF = (c) => (String(c || '').length === 14 ? String(c).replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5') : c || '');
  const curto = (p) => String(p || '').split(/[\\/]/).slice(-3).join('\\');
  const conta = (root) => root.querySelectorAll('[data-n]').forEach((el) => {
    const alvo = Number(el.dataset.n) || 0, brl = el.dataset.fmt === 'brl', t0 = performance.now();
    const f = (v) => (brl ? 'R$ ' + fm(v) : Math.round(v).toLocaleString('pt-BR'));
    const passo = (t) => { const k = Math.min(1, (t - t0) / 900); el.textContent = f(alvo * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(passo); };
    requestAnimationFrame(passo);
  });
  const box = () => $('#corrLote');
  const fechar = () => { box().hidden = true; $('#corrSpedEmpty').hidden = false; };
  const tipoRot = { difal: 'DIFAL', frete: 'Frete (CT-e)', balcao: 'Balcão', credito: 'Crédito uso e consumo', simples_aliq: 'Simples · alíquota', simples_sem: 'Simples · sem direito', e116: 'Guia E116' };
  const nAuto = (e) => ((e.correcoes || {}).total || 0) + ((e.auto || {}).cfop || []).length + ((e.auto || {}).simples || []).length + ((e.auto || {}).icms_xml || []).length + ((e.auto || {}).valor_xml || []).length;
  const idx = (e) => L.an.empresas.indexOf(e);

  async function analisar() {
    overlay(true, 'Lendo os SPEDs do mês e procurando os XMLs de entrada…');
    const r = await window.fiscocont.admin.loteAnalisar({ pasta: L.pasta, pastaXmls: L.pastaXmls });
    overlay(false);
    if (r.error) { toast(r.error, true); return; }
    L.an = r.res; L.esc = {}; L.usar = {}; L.res = null;
    L.an.empresas.forEach((e, i) => { L.usar[i] = !e.erro && !e.outro_periodo && !e.duplicado; L.esc[i] = {}; });
    render();
  }

  function decisaoHtml(i, d) {
    const atual = L.esc[i][d.id] ?? d.padrao;
    const v = typeof atual === 'object' ? atual.v : atual;
    const nome = `ld-${i}-${d.id}`;
    return `<div class="lote-dec" data-e="${i}" data-id="${esc(d.id)}">
      <div class="lote-dec-t"><span class="lote-tag t-${d.tipo}">${tipoRot[d.tipo] || d.tipo}</span><b>${esc(d.titulo)}</b>
        ${d.valor ? `<span class="lote-dec-v">R$ ${fm(d.valor)}</span>` : ''}</div>
      <div class="lote-dec-n">${esc(d.nota)}</div>
      ${d.detalhe ? `<div class="lote-dec-d">${esc(d.detalhe)}</div>` : ''}
      <div class="lote-ops">${d.opcoes.map((o) => `<label><input type="radio" name="${esc(nome)}" value="${o.v}" ${o.v === v ? 'checked' : ''}> ${esc(o.rot)}${o.v === d.padrao ? ' <small>(sugerido)</small>' : ''}</label>`).join('')}
        ${d.entrada === 'aliq' ? `<input class="lote-aliq" placeholder="alíquota %" value="${esc(typeof atual === 'object' ? atual.aliq : '')}">` : ''}</div>
    </div>`;
  }
  function e116Html(i, e) {
    const at = L.esc[i].e116 || {}, ex = e.e116_existente || {};
    return `<div class="lote-dec" data-e="${i}" data-id="e116">
      <div class="lote-dec-t"><span class="lote-tag t-e116">Guia E116</span><b>Empresa passa a ter ICMS a recolher e o SPED não tem guia</b></div>
      <div class="lote-dec-d">Informe o vencimento e o código de receita da guia de ICMS normal (E116, obrigação 000).</div>
      <div class="lote-ops"><label>Vencimento <input class="lote-venc" placeholder="dd/mm/aaaa" value="${esc(at.venc ? dt(at.venc) : (ex.venc ? dt(ex.venc) : ''))}"></label>
        <label>Código de receita <input class="lote-cod" placeholder="ex.: 1210" value="${esc(at.cod_rec || ex.cod_rec || '')}"></label></div>
    </div>`;
  }

  function render() {
    const an = L.an, emp = an.empresas, b = box();
    const ativos = emp.filter((e, i) => L.usar[i]);
    const nDec = ativos.reduce((t, e) => t + (e.decisoes || []).length + (e.precisa_e116 ? 1 : 0), 0);
    const antes = ativos.reduce((t, e) => t + (e.icms_antes || 0), 0);
    const depois = ativos.reduce((t, e) => t + (e.icms_depois ?? e.icms_antes ?? 0), 0);
    const fora = emp.filter((e) => e.outro_periodo), dups = emp.filter((e) => e.duplicado), errs = emp.filter((e) => e.erro && !e.precisa_e116);
    b.innerHTML = `
      <div class="dif-head"><div>
        <div class="dif-k">Correção do SPED Fiscal · Admin · ⚡ Automatizar correção</div>
        <h3>Correção automática — ${esc(an.mes || 'mês não identificado')}</h3>
        <div class="dif-sub">SPEDs em <b>${esc(curto(an.pasta))}</b> · XMLs de entrada procurados em <b>${esc(curto(an.pasta_xmls))}\\&lt;CLIENTE&gt;\\NF-e\\Entradas</b></div>
      </div><div class="lote-hbtn"><button class="act inv-export" id="btnLoteXmls">Trocar pasta dos XMLs</button><button class="act inv-export" id="btnLoteFechar">Fechar</button></div></div>
      <div class="dif-lei">Mesmo motor do modo manual (<b>Corrigir SPED</b> → <b>Uso e consumo · DIFAL e crédito</b> → <b>Crédito Simples Nacional</b>).
        O que é certo já vai aplicado: erros de validação, CFOP 1.xxx × 2.xxx pela UF do fornecedor, crédito de ICMS acima do destacado no XML e crédito do Simples informado no XML.
        O resto fica em <b>Decisões pendentes</b>, com a sugestão já marcada. Notas faltantes não entram aqui. Os originais nunca são alterados.</div>
      <div class="dif-kpis">
        <div><span>SPEDs encontrados</span><b data-n="${emp.length}">0</b><small>${ativos.length} no lote</small></div>
        <div><span>Com XML de entrada</span><b data-n="${emp.filter((e) => e.xmls).length}">0</b><small>${emp.filter((e) => !e.xmls).length} só pelo SPED</small></div>
        <div class="k-ok"><span>Correções automáticas</span><b data-n="${ativos.reduce((t, e) => t + nAuto(e), 0)}">0</b><small>sem precisar decidir</small></div>
        <div class="k-warn"><span>Decisões pendentes</span><b data-n="${nDec}">0</b><small>já com a sugestão marcada</small></div>
        <div class="k-err"><span>ICMS a recolher (com as sugestões)</span><b data-n="${depois}" data-fmt="brl">R$ 0,00</b><small>antes R$ ${fm(antes)}</small></div>
      </div>
      ${fora.length ? `<div class="dif-av err"><b>SPED de outro período nesta pasta (fora do lote):</b><ul>${fora.map((e) => `<li>${esc(e.arquivo)} — ${esc(e.empresa.nome)}: período ${esc(e.mes_sped)}, pasta ${esc(an.mes)}</li>`).join('')}</ul></div>` : ''}
      ${dups.length ? `<div class="dif-av"><b>Mesmo CNPJ e período em mais de um arquivo (fora do lote):</b><ul>${dups.map((e) => `<li>${esc(e.arquivo)} repete ${esc(e.duplicado)} — ${esc(e.empresa.nome)}</li>`).join('')}</ul></div>` : ''}
      ${errs.length ? `<div class="dif-av err"><b>Não deu para corrigir:</b><ul>${errs.map((e) => `<li>${esc(e.arquivo)}: ${esc(e.erro)}</li>`).join('')}</ul></div>` : ''}
      ${(an.clientes_sem_sped || []).length ? `<div class="dif-av"><b>Clientes com XML de entrada mas sem SPED nesta pasta:</b> ${an.clientes_sem_sped.map(esc).join(', ')}</div>` : ''}
      <div class="lote-sec">Clientes</div>
      <div class="lote-lista">${emp.map((e, i) => {
        const nd = (e.decisoes || []).length + (e.precisa_e116 ? 1 : 0);
        const chips = [];
        if ((e.correcoes || {}).total) chips.push(`${e.correcoes.total} de validação`);
        if ((e.auto || {}).cfop?.length) chips.push(`${e.auto.cfop.length} CFOP`);
        if ((e.auto || {}).simples?.length) chips.push(`${e.auto.simples.length} Simples`);
        if ((e.auto || {}).icms_xml?.length) chips.push(`${e.auto.icms_xml.length} crédito × XML`);
        if ((e.auto || {}).valor_xml?.length) chips.push(`${e.auto.valor_xml.length} valor/base × XML`);
        const dep = e.icms_depois ?? e.icms_antes;
        const st = e.outro_periodo ? ['b-err', 'outro período'] : e.duplicado ? ['b-warn', 'duplicado'] : (e.erro && !e.precisa_e116) ? ['b-err', 'erro']
          : nd ? ['b-warn', `${nd} decisão(ões)`] : (nAuto(e) || e.alterado) ? ['b-ok', 'pronto'] : ['b-ok', 'nada a corrigir'];
        return `<div class="lote-cli ${L.usar[i] ? '' : 'off'}" style="--i:${i}">
          <label class="lote-usa" title="Incluir no lote"><input type="checkbox" class="lote-ck" data-e="${i}" ${L.usar[i] ? 'checked' : ''} ${e.erro && !e.precisa_e116 ? 'disabled' : ''}></label>
          <div class="lote-cli-n"><b>${esc(e.empresa?.nome || e.arquivo)}</b>
            <small>${esc(cnpjF(e.empresa?.cnpj))} · ${dt(e.empresa?.dt_ini)} a ${dt(e.empresa?.dt_fin)} · ${esc(e.arquivo)}</small>
            <div class="lote-chips"><span class="lote-chip ${e.xmls ? 'xml' : 'sem'}" title="${esc(e.xmls || '')}">${e.xmls ? `XML: ${e.xml_lidos} lido(s)` : 'sem XML — só pelo SPED'}</span>
              ${chips.map((c) => `<span class="lote-chip">${c}</span>`).join('')}</div></div>
          <div class="lote-cli-v"><small>ICMS a recolher</small>R$ ${fm(e.icms_antes)} <i>→</i> <b>R$ ${fm(dep)}</b></div>
          <div class="lote-cli-a"><span class="dif-b ${st[0]}">${st[1]}</span><button class="act inv-export lote-man" data-e="${i}">Abrir no modo manual</button></div>
        </div>`;
      }).join('')}</div>
      <div class="lote-sec">Decisões pendentes ${nDec ? `<span class="dif-b b-warn">${nDec}</span>` : ''}</div>
      ${nDec ? emp.map((e, i) => (!L.usar[i] || !((e.decisoes || []).length || e.precisa_e116)) ? '' : `
        <div class="lote-grupo"><div class="lote-grupo-t">${esc(e.empresa.nome)}</div>
          ${(e.decisoes || []).map((d) => decisaoHtml(i, d)).join('')}${e.precisa_e116 ? e116Html(i, e) : ''}</div>`).join('')
        : '<div class="dif-av ok">Nenhuma decisão pendente — é só aplicar.</div>'}
      <div class="dif-acts"><button class="act inv-export" id="btnLoteAplicar" style="background:#e23d4c;color:#fff;border-color:transparent" ${ativos.length ? '' : 'disabled'}>⚡ Aplicar e gerar ${ativos.length} SPED(s) corrigido(s)</button></div>`;
    b.hidden = false;
    $('#corrSpedEmpty').hidden = true; $('#corrSpedFrame').hidden = true; $('#corrSpedResumo').hidden = true;
    $('#corrDifal').hidden = true; $('#corrSimples').hidden = true;
    conta(b);
    $('#btnLoteFechar').addEventListener('click', fechar);
    $('#btnLoteXmls').addEventListener('click', async () => {
      const p = await window.fiscocont.admin.lotePickPasta({ titulo: 'Pasta do mês (MM-AAAA) onde estão as pastas dos clientes com NF-e\\Entradas' });
      if (p.canceled || !p.path) return;
      L.pastaXmls = p.path; analisar();
    });
    b.querySelectorAll('.lote-ck').forEach((c) => c.addEventListener('change', () => { lerEscolhas(); L.usar[c.dataset.e] = c.checked; render(); }));
    b.querySelectorAll('.lote-man').forEach((x) => x.addEventListener('click', () => {
      const e = emp[x.dataset.e];
      if (window.__corrAbrirManual) window.__corrAbrirManual(e.sped, e.xmls);
    }));
    $('#btnLoteAplicar').addEventListener('click', aplicar);
  }

  function lerEscolhas() {
    box().querySelectorAll('.lote-dec').forEach((el) => {
      const i = el.dataset.e, id = el.dataset.id;
      if (id === 'e116') {
        L.esc[i].e116 = { venc: (el.querySelector('.lote-venc').value || '').replace(/\D/g, ''), cod_rec: (el.querySelector('.lote-cod').value || '').trim() };
        return;
      }
      const r = el.querySelector('input[type=radio]:checked');
      if (!r) return;
      const a = el.querySelector('.lote-aliq');
      L.esc[i][id] = a ? { v: r.value, aliq: (a.value || '').replace(',', '.').trim() } : r.value;
    });
  }

  async function aplicar() {
    lerEscolhas();
    const emp = L.an.empresas, arquivos = [];
    for (let i = 0; i < emp.length; i++) {
      if (!L.usar[i]) continue;
      const e = emp[i], d = { ...L.esc[i] };
      for (const x of e.decisoes || []) {
        const v = d[x.id];
        if (x.entrada === 'aliq' && v && v.v === 'aliq' && !(Number(v.aliq) > 0)) { toast(`${e.empresa.nome}: informe a alíquota do Simples da ${x.nota}.`, true); return; }
      }
      if (e.precisa_e116) {
        const g = d.e116 || {};
        if (g.venc?.length !== 8 || !g.cod_rec) { toast(`${e.empresa.nome}: informe o vencimento (dd/mm/aaaa) e o código de receita da guia E116.`, true); return; }
      } else delete d.e116;
      arquivos.push({ sped: e.sped, xmls: e.xmls, decisoes: d });
    }
    overlay(true, `Corrigindo ${arquivos.length} SPED(s)…`);
    const r = await window.fiscocont.admin.loteAplicar({ plano: { mes: L.an.mes, arquivos } });
    overlay(false);
    if (r.error) { toast(r.error, true); return; }
    L.res = r.res;
    renderRes();
  }

  function renderRes() {
    const res = L.res, emp = res.empresas || [], b = box();
    const ok = emp.filter((e) => e.corrigido), err = emp.filter((e) => !e.corrigido);
    const antes = ok.reduce((t, e) => t + (e.icms_antes || 0), 0), depois = ok.reduce((t, e) => t + (e.icms_depois || 0), 0);
    const difal = ok.reduce((t, e) => t + ((e.difal || {}).incluido || 0) - ((e.difal || {}).removido || 0), 0);
    const sn = ok.reduce((t, e) => t + ((e.simples || {}).credito || 0), 0);
    b.innerHTML = `
      <div class="dif-head"><div>
        <div class="dif-k">⚡ Automatizar correção · resultado</div>
        <h3>Correção automática — ${esc(res.mes || '')}</h3>
        <div class="dif-sub">${ok.length} SPED(s) corrigido(s)${err.length ? ` · ${err.length} com erro` : ''}. Valide cada arquivo no PVA antes de transmitir.</div>
      </div><div class="lote-hbtn"><button class="act inv-export" id="btnLoteVoltar">Voltar às decisões</button><button class="act inv-export" id="btnLoteFechar2">Fechar</button></div></div>
      <div class="dif-kpis">
        <div class="k-ok"><span>SPEDs corrigidos</span><b data-n="${ok.length}">0</b><small>arquivos novos</small></div>
        <div><span>ICMS a recolher antes</span><b data-n="${antes}" data-fmt="brl">R$ 0,00</b><small>soma do E110 (campo 13)</small></div>
        <div class="k-err"><span>ICMS a recolher depois</span><b data-n="${depois}" data-fmt="brl">R$ 0,00</b><small>${depois >= antes ? '+' : '−'} R$ ${fm(Math.abs(depois - antes))}</small></div>
        <div class="k-warn"><span>DIFAL lançado (líquido)</span><b data-n="${difal}" data-fmt="brl">R$ 0,00</b><small>C197/D197</small></div>
        <div class="k-ok"><span>Crédito do Simples</span><b data-n="${sn}" data-fmt="brl">R$ 0,00</b><small>C197 RO00000001</small></div>
      </div>
      <div class="dif-tw"><table class="dif-tab"><thead><tr><th>Cliente</th><th>Situação</th><th class="n">ICMS antes</th><th class="n">ICMS depois</th><th class="n">DIFAL</th><th class="n">Crédito × XML</th><th class="n">Simples</th><th>Atenção</th><th></th></tr></thead>
        <tbody>${emp.map((e, k) => `<tr>
          <td><b>${esc(e.empresa?.nome || e.arquivo)}</b><small>${esc(e.arquivo)}</small></td>
          <td>${e.corrigido ? '<span class="dif-b b-ok">corrigido</span>' : `<span class="dif-b b-err">erro</span><small style="white-space:normal">${esc(e.erro || '')}</small>`}</td>
          <td class="n">R$ ${fm(e.icms_antes)}</td><td class="n"><b>R$ ${fm(e.icms_depois ?? e.icms_antes)}</b></td>
          <td class="n">R$ ${fm(((e.difal || {}).incluido || 0) - ((e.difal || {}).removido || 0))}</td><td class="n">${((e.icms_xml || {}).credito_retirado || 0) + ((e.valor_xml || {}).credito_retirado || 0) ? '− R$ ' + fm(((e.icms_xml || {}).credito_retirado || 0) + ((e.valor_xml || {}).credito_retirado || 0)) : '—'}</td><td class="n">R$ ${fm((e.simples || {}).credito)}</td>
          <td style="max-width:320px;white-space:normal;font-size:11.5px">${(e.avisos || []).map(esc).join('<br>')}</td>
          <td><div class="lote-tdb">${e.corrigido ? `<button class="act inv-export lote-baixa" data-k="${k}">Baixar</button>` : ''}
            <button class="act inv-export lote-man2" data-k="${k}">Modo manual</button></div></td></tr>`).join('')}</tbody></table></div>
      <div class="dif-acts">${res.zip ? '<button class="act inv-export" id="btnLoteZip" style="background:#0ea472;color:#fff;border-color:transparent">Baixar todos (.zip)</button>' : ''}</div>`;
    b.hidden = false;
    conta(b);
    $('#btnLoteFechar2').addEventListener('click', fechar);
    $('#btnLoteVoltar').addEventListener('click', render);
    const salvar = async (arquivo) => {
      const r = await window.fiscocont.admin.loteSalvar({ arquivo });
      if (r.canceled) return;
      if (r.error) { toast(r.error, true); return; }
      toast('Salvo em ' + r.path);
    };
    if (res.zip) $('#btnLoteZip').addEventListener('click', () => salvar(res.zip));
    b.querySelectorAll('.lote-baixa').forEach((x) => x.addEventListener('click', () => salvar(emp[x.dataset.k].corrigido)));
    b.querySelectorAll('.lote-man2').forEach((x) => x.addEventListener('click', () => {
      const e = emp[x.dataset.k];
      if (window.__corrAbrirManual) window.__corrAbrirManual(e.sped, e.xmls);
    }));
    toast(`${ok.length} SPED(s) corrigido(s).`);
  }

  btn.addEventListener('click', async () => {
    const p = await window.fiscocont.admin.lotePickPasta({});
    if (p.canceled || !p.path) return;
    L.pasta = p.path; L.pastaXmls = null;
    analisar();
  });
}

function bindBaixaLote() {
  const btn = $('#btnNflBaixar');
  if (!btn) return;
  const modal = $('#nflModal');
  const fmt = (iso) => (iso ? iso.split('-').reverse().join('/') : '');
  let totalEmp = 0;
  let rodando = false;
  const MSG = { vazio: 'O período é obrigatório: informe a data inicial e a data final para continuar.', ordem: 'A data inicial não pode ser depois da data final.' };

  function validar() {
    const ini = $('#nflIni').value;
    const fim = $('#nflFim').value;
    const conf = $('#nflConfirma');
    const ok = !!ini && !!fim && ini <= fim;
    if (!ini || !fim) conf.textContent = MSG.vazio;
    else if (ini > fim) conf.textContent = MSG.ordem;
    else conf.textContent = `Serão baixadas as NFS-e de ${fmt(ini)} a ${fmt(fim)} de ${totalEmp} empresa(s) cadastrada(s), uma por vez. O painel de cada empresa é salvo na pasta dela e o relatório geral na pasta "_Relatorios em lote".`;
    $('#btnNflIniciar').disabled = !ok;
  }
  $('#nflIni').addEventListener('input', validar);
  $('#nflFim').addEventListener('input', validar);

  btn.addEventListener('click', async () => {
    if (rodando) return;
    const lista = await window.fiscocont.fiscal.certListar();
    totalEmp = lista.length;
    $('#nflIni').value = '';
    $('#nflFim').value = '';
    $('#nflIntro').textContent = `Baixa as NFS-e de todas as ${totalEmp} empresa(s) cadastrada(s), uma de cada vez. Escolha o período antes de começar.`;
    $('#nflForm').hidden = false;
    $('#nflProg').hidden = true;
    validar();
    modal.hidden = false;
  });
  $('#btnNflFechar').addEventListener('click', () => { modal.hidden = true; });

  $('#btnNflCancelarLote').addEventListener('click', async () => {
    $('#btnNflCancelarLote').disabled = true;
    $('#nflAtual').textContent += ' — cancelando ao fim desta empresa…';
    await window.fiscocont.fiscal.nfseLoteCancelar();
  });

  $('#btnNflIniciar').addEventListener('click', async () => {
    const ini = $('#nflIni').value;
    const fim = $('#nflFim').value;
    if (!ini || !fim || ini > fim || rodando) return;      // defesa: sem período válido o lote não começa
    const gerarPdf = $('#nflGerarPdf').checked;
    rodando = true;
    $('#nflForm').hidden = true;
    $('#nflProg').hidden = false;
    $('#nflLog').innerHTML = '';
    $('#nflBarra').style.width = '0%';
    $('#btnNflCancelarLote').disabled = false;
    $('#nflAtual').textContent = 'Preparando…';
    const rotulo = { concluida: '✓', sem_notas: '·', pulada: '⚠', erro: '✗' };
    const off = window.fiscocont.fiscal.onNfseLoteProgresso((p) => {
      if (p.fase === 'inicio') {
        $('#nflAtual').textContent = `Empresa ${p.i} de ${p.total}: ${p.nome}…`;
        $('#nflBarra').style.width = `${Math.round(((p.i - 1) / p.total) * 100)}%`;
      } else {
        const txt = p.status === 'concluida' ? `${p.salvos} nota(s)` : (p.status === 'sem_notas' ? 'sem notas no período' : (p.motivo || p.status));
        $('#nflLog').insertAdjacentHTML('beforeend', `<div>${rotulo[p.status] || '·'} <b>${_esc(p.nome)}</b> — ${_esc(txt)}</div>`);
        $('#nflLog').scrollTop = $('#nflLog').scrollHeight;
        $('#nflBarra').style.width = `${Math.round((p.i / p.total) * 100)}%`;
      }
    });
    let res;
    try {
      res = await window.fiscocont.fiscal.nfseLoteIniciar({ dataInicial: ini, dataFinal: fim, gerarPdf });
    } finally {
      rodando = false;
      off();
      modal.hidden = true;
    }
    document.dispatchEvent(new Event('fiscocont:dl-recarregar'));
    if (res.error) { toast(res.error, true); return; }
    const r = res.resumo;
    const box = $('#nflResultado');
    box.hidden = false;
    $('#nflResumoTexto').innerHTML = `<b>${r.salvos}</b> NFS-e baixadas · ${r.concluidas} empresa(s) concluída(s) · ${r.sem_notas} sem notas · <b>${r.puladas + r.erros}</b> não baixada(s) ou com erro${r.nao_iniciadas ? ` · ${r.nao_iniciadas} não iniciada(s)` : ''}${r.cancelado ? ' · <b>lote cancelado</b>' : ''}`;
    $('#nflCaminho').textContent = `Relatório salvo em: ${res.caminho}`;
    $('#nflFrame').src = res.url;
    $('#btnNflAbrirPasta').onclick = () => window.fiscocont.openPath(res.pasta);
    $('#btnNflAbrirRel').onclick = () => window.fiscocont.abrirArquivo(res.caminho);
    if (r.concluidas + r.sem_notas === 0 && !r.cancelado) toast(`Nenhuma empresa foi baixada (${r.puladas + r.erros} com problema) — veja os motivos no relatório.`, true);
    else toast(r.cancelado ? 'Lote cancelado — o relatório do que foi feito está salvo.' : `Lote concluído: ${r.salvos} nota(s) de ${r.concluidas} empresa(s).`);
  });
}

// Letreiro de notícias na faixa do topo (substituiu o balão): as manchetes passam da direita para a esquerda,
// param com o mouse em cima, clique abre a notícia, ✕ desativa (reativa no rodapé do menu). Nas telas do
// Contábil com balancete aberto, a faixa volta a mostrar a empresa do balancete.
var _newsAtivo = true, _newsLista = [];
function _atualizaTopo() {
  const tk = $('#newsTk'); if (!tk) return;
  const info = $('#topInfo');
  const balancete = !!(info && DATA && document.body.dataset.areaContabil !== '');
  if (info) info.hidden = !balancete;
  const mostra = _newsAtivo && _newsLista.length > 0 && !balancete;
  tk.hidden = !mostra;
  const tb = tk.closest('.topbar'); if (tb) tb.classList.toggle('com-news', mostra);
}
function bindNewsToast() {
  const tk = $('#newsTk');
  if (!tk || !window.fiscocont.news) return;
  const track = $('#newsTrack');
  let assinatura = '';

  function desenhar() {
    const sig = _newsLista.map((i) => i.guid).join('|');
    if (sig === assinatura) return;
    assinatura = sig;
    const um = _newsLista.map((i) => `<span class="tk-it" data-link="${_esc(i.link)}" title="Abrir a notícia no navegador"><b>${_esc(i.categoria)}</b>${_esc(i.titulo)}</span>`).join('');
    track.innerHTML = um + um;   // duas cópias: o letreiro roda sem emenda
    requestAnimationFrame(() => {
      const larg = track.scrollWidth / 2;
      track.style.setProperty('--tk-dur', Math.max(30, Math.round(larg / 55)) + 's');   // ~55 px por segundo, dá para ler
    });
  }

  window.fiscocont.news.onLista((lista) => {
    _newsLista = Array.isArray(lista) ? lista.filter((i) => i && i.titulo) : [];
    desenhar(); _atualizaTopo();
  });
  window.fiscocont.news.avisarPronto();

  track.addEventListener('click', (ev) => {
    const it = ev.target.closest('.tk-it');
    if (it && it.dataset.link) window.fiscocont.news.abrirLink(it.dataset.link);
  });
  $('#newsTkX').addEventListener('click', async () => {
    await window.fiscocont.news.desativar();
    _newsAtivo = false; _atualizaTopo(); atualizarLinkRodape();
    toast('Notícias desativadas. Para reativar, use o link no rodapé do menu.');
  });

  const linkRodape = $('#newsToggleLink');
  async function atualizarLinkRodape() {
    if (!linkRodape) return;
    const status = await window.fiscocont.news.status();
    _newsAtivo = status !== 'desativado';
    linkRodape.textContent = _newsAtivo ? '📰 notícias: ativas (desativar)' : '📰 notícias: desativadas (reativar)';
    _atualizaTopo();
  }
  if (linkRodape) {
    linkRodape.addEventListener('click', async () => {
      const status = await window.fiscocont.news.status();
      if (status === 'desativado') await window.fiscocont.news.ativar();
      else await window.fiscocont.news.desativar();
      await atualizarLinkRodape();
    });
  }
  atualizarLinkRodape();
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
  initAdminModulos();

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

  // Selos com data fixa de validade (7 dias a partir do lançamento): EFD-Contribuições (07/10/2026)
  // e Manual do Fiscal (26/10/2026, selo "NOVIDADE" em destaque).
  [['#efdNewBadge', '2026-10-14T23:59:59'], ['#manualNewBadge', '2026-11-02T23:59:59']].forEach(([sel, ate]) => {
    const b = $(sel); if (b && new Date() <= new Date(ate)) b.hidden = false;
  });
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
  setInterval(() => checkLicenseGate(false), 15 * 60 * 1000); // rede de segurança, caso o listener em tempo real caia sem avisar
  const licRefresh = $('#btnLicRefresh');
  if (licRefresh) licRefresh.addEventListener('click', loadLicensePanel);

  bindAtualizacao();
  bindManual();
  bindManifestacao();
  const ubClose = $('#updateBannerClose');
  if (ubClose) ubClose.addEventListener('click', () => { $('#updateBanner').hidden = true; });

  bindLogin();
  bindUsuarios();
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
  bindCorrigirEfd();
  bindLoteSped();
  bindBaixaLote();
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

// ================================================================== módulos Admin (teste)
// Radar de Oportunidades Fiscais + Levantamento Legalização. Só aparecem para o papel Admin
// (menu "admin-only") e os handlers do processo principal também exigem Admin.
const ADM = {
  radar: { efdc: [], fiscal: [], xml: [], res: null, status: {}, filtro: 'Todos', aberta: null },
  legal: { cnpj: '', res: null, itens: {}, sujo: false },
};
const escA = (s) => esc(s).replace(/"/g, '&quot;');
const ADM_TIPO = { monofasico: 'PIS/COFINS monofásico', tema69: 'ICMS na base do PIS/COFINS', ciap: 'CIAP' };
const ADM_COR = { monofasico: '#2a78d6', tema69: '#eb6834', ciap: '#1baf7a' };
const admNome = (p) => String(p).split(/[\\/]/).pop();

function admContar(el, ate, dinheiro) {
  if (!el) return;
  const t0 = performance.now(), dur = 800;
  function passo(t) {
    const k = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - k, 3);
    el.textContent = dinheiro ? brl(ate * e) : Math.round(ate * e).toLocaleString('pt-BR');
    if (k < 1) requestAnimationFrame(passo);
  }
  requestAnimationFrame(passo);
}
const admMes = (c) => (c && c.length === 7 ? c.slice(5) + '/' + c.slice(0, 4) : c);
const admData = (iso) => (iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4) : '');

// ------------------------------------------------------------------ Auditoria ICMS/AM
// Painel em dashboard: resumo (KPIs), gravidade, ranking das verificações, conciliação
// E110 × C190, cobertura do arquivo e lista filtrável de apontamentos com base legal.
const AUDAM = { sped: [], res: null, filtro: 'todos', busca: '', aberta: null };
const audEsc = (x) => String(x == null ? '' : x).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const AUD_GRAV = {
  Alta: { cor: '#dc3856', cls: 'alta' },
  'Média': { cor: '#e8901c', cls: 'media' },
  Baixa: { cor: '#7c8db5', cls: 'baixa' },
};
const AUD_FAM = { A: 'Base legal', B: 'Regra de escrituração' };
const AUD_COL = {
  motivo: 'Por que foi apontado', nota: 'Nota', item: 'Item', origem: 'Origem', cod: 'Código', descr: 'Descrição', ncm: 'NCM', cest: 'CEST', cst: 'CST', cfop: 'CFOP',
  aliq: 'Alíq. %', bc: 'Base', icms: 'ICMS', valor_item: 'Valor item', esperado: 'ICMS esperado', anexo: 'Anexo',
  segmento: 'Segmento', cest_lista: 'CEST da lista', cest_candidatos: 'CEST possíveis', qtd_candidatos: 'Qtd. possíveis',
  bc_itens: 'Base itens', bc_c190: 'Base C190', icms_itens: 'ICMS itens', icms_c190: 'ICMS C190',
};
const AUD_MOEDA = new Set(['bc', 'icms', 'valor_item', 'esperado', 'bc_itens', 'bc_c190', 'icms_itens', 'icms_c190']);
const audId = (a) => a.regra + '|' + a.titulo;
const audNum = (n) => new Intl.NumberFormat('pt-BR').format(n || 0);

function audCel(k, v) {
  if (Array.isArray(v)) return audEsc(v.join(', '));
  if (AUD_MOEDA.has(k) && typeof v === 'number') return nf.format(v);
  if (k === 'aliq' && typeof v === 'number') return nf.format(v);
  return audEsc(v);
}

function audExemplos(a) {
  const ex = a.exemplos || [];
  if (!ex.length) return '';
  const cols = [];
  ex.forEach((e) => Object.keys(e).forEach((k) => { if (!cols.includes(k)) cols.push(k); }));
  if (cols.includes('motivo')) cols.splice(0, cols.length, 'motivo', ...cols.filter((k) => k !== 'motivo'));
  const num = (k) => AUD_MOEDA.has(k) || k === 'aliq' || k === 'qtd_candidatos';
  const head = cols.map((k) => `<th class="${num(k) ? 'n' : ''}">${audEsc(AUD_COL[k] || k)}</th>`).join('');
  const rows = ex.map((e) => '<tr>' + cols.map((k) => `<td class="${num(k) ? 'n' : ''}${k === 'motivo' ? ' aud-mot' : ''}">${e[k] == null || e[k] === '' ? '<span class="aud-vazio">—</span>' : audCel(k, e[k])}</td>`).join('') + '</tr>').join('');
  return `<div class="aud-sub">Exemplos ${a.qtd > ex.length ? `<span>· ${ex.length} de ${audNum(a.qtd)} ocorrências</span>` : ''}</div>
    <div class="aud-tabwrap"><table class="aud-tab"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

const AUD_STATUS = {
  lida: ['ok', 'texto oficial lido'],
  indireta: ['av', 'aplicação direta da lei'],
};
function audBaseHTML(b, compacto) {
  if (!b) return '<div class="adm-lg aud-semlei"><b class="t">Sem dispositivo associado</b>Verificação sem norma vinculada.</div>';
  const st = AUD_STATUS[b.status] || ['av', 'não confirmada'];
  const disp = (b.dispositivos || []).map((d) => `<div class="aud-disp">
      <div class="aud-disp-h"><b>${audEsc(d.ref)}</b><a href="${audEsc(d.url)}" target="_blank" rel="noopener">texto oficial ↗</a></div>
      <blockquote>“${audEsc(d.texto)}”</blockquote></div>`).join('');
  return `<div class="adm-lg aud-base"><b class="t">Fundamento ${compacto ? '' : `<span class="adm-pill ${st[0]}">${st[1]}</span>`}${b.lido_em ? `<span class="aud-lido">lido em ${audEsc(b.lido_em)}</span>` : ''}</b>
      <div class="aud-norma-full">${audEsc(b.norma)}</div>
      ${b.resumo ? `<p class="aud-resumo">${audEsc(b.resumo)}</p>` : ''}
      ${disp}
      ${b.nao_conferido ? `<div class="fn"><b>Limite da verificação:</b> ${audEsc(b.nao_conferido)}</div>` : ''}</div>`;
}

function audDetalhe(a) {
  return `<div class="adm-det"><p>${audEsc(a.descricao)}</p>${audBaseHTML(a.base_legal)}
    ${a.como_verificar ? `<div class="adm-lg at"><b class="t">Como verificar</b>${audEsc(a.como_verificar)}</div>` : ''}
    ${audExemplos(a)}</div>`;
}

function audLista() {
  const res = AUDAM.res, f = AUDAM.filtro, q = AUDAM.busca.trim().toLowerCase();
  const L = (res.achados || []).filter((a) =>
    (f === 'todos' || a.familia === f || a.gravidade === f) &&
    (!q || (a.titulo + ' ' + a.descricao + ' ' + ((a.base_legal || {}).norma || '') + ' ' + ((a.base_legal || {}).dispositivos || []).map((d) => d.ref + ' ' + d.texto).join(' ')).toLowerCase().includes(q)));
  if (!L.length) return '<div class="aud-nada">Nenhum apontamento com esse filtro.</div>';
  return L.map((a, i) => {
    const g = AUD_GRAV[a.gravidade] || AUD_GRAV.Baixa, id = audId(a);
    return `<div class="adm-op aud-op ${g.cls}${AUDAM.aberta === id ? ' aberta' : ''}" data-audid="${audEsc(id)}" style="animation:admUp .35s ease both;animation-delay:${Math.min(i, 12) * .04}s">
      <div class="adm-op-h" data-abrirauda="${audEsc(id)}">
        <div><b>${audEsc(a.titulo)}</b>
          <small><span class="aud-sev ${g.cls}">${audEsc(a.gravidade)}</span><span class="adm-pill ${a.familia === 'A' ? 'rx' : 'na'}">${AUD_FAM[a.familia] || a.familia}</span>${a.base_legal ? `<span class="aud-norma">${audEsc(a.base_legal.norma)}</span>` : ''}</small></div>
        <div class="aud-op-n"><b>${audNum(a.qtd)}</b><span>ocorrência${a.qtd === 1 ? '' : 's'}</span>${a.valor ? `<em>${brl(a.valor)}</em>` : ''}</div>
      </div>${audDetalhe(a)}</div>`;
  }).join('');
}

function audConciliacao(conc) {
  if (!conc.length) return '';
  const linhas = conc.map((c, i) => {
    const max = Math.max(Math.abs(c.e110), Math.abs(c.c190), 0.01);
    const ok = Math.abs(c.dif) < 0.01;
    const w = (v) => Math.max(Math.abs(v) / max * 100, v ? 2 : 0).toFixed(1) + '%';
    return `<div class="aud-conc">
      <div class="aud-conc-h"><b>${audEsc(c.titulo)}</b>${ok ? '<span class="adm-pill ok">Fecha</span>' : `<span class="adm-pill no">Diferença ${brl(c.dif)}</span>`}</div>
      <div class="aud-bar"><span>E110</span><div class="tr"><b style="--w:${w(c.e110)};background:var(--adm);animation-delay:${i * .15}s"></b></div><em>${brl(c.e110)}</em></div>
      <div class="aud-bar"><span>C190</span><div class="tr"><b style="--w:${w(c.c190)};background:#0ea5e9;animation-delay:${i * .15 + .08}s"></b></div><em>${brl(c.c190)}</em></div>
      ${c.nota ? `<small>${audEsc(c.nota)}</small>` : ''}
      ${c.base_legal ? `<details class="aud-conc-base"><summary>Fundamento: ${audEsc((c.base_legal.dispositivos[0] || {}).ref || c.base_legal.norma)}</summary>${audBaseHTML(c.base_legal, true)}</details>` : ''}</div>`;
  }).join('');
  return `<div class="adm-card"><h3>Conciliação da apuração · E110 × C190</h3>${linhas}</div>`;
}

function audRender() {
  const res = AUDAM.res, el = $('#audPainel');
  if (!res) { el.innerHTML = ''; el.hidden = true; return; }
  const A = res.achados || [], cb = res.cobertura || {}, cli = res.cliente || {};
  const tot = A.reduce((s, a) => s + a.qtd, 0);
  const valor = A.reduce((s, a) => s + (a.valor || 0), 0);
  const porGrav = { Alta: 0, 'Média': 0, Baixa: 0 };
  A.forEach((a) => { porGrav[a.gravidade] = (porGrav[a.gravidade] || 0) + a.qtd; });
  const fam = (k) => A.filter((a) => a.familia === k).reduce((s, a) => s + a.qtd, 0);
  const famA = fam('A'), famB = fam('B');

  // donut de gravidade
  const segs = Object.entries(porGrav).filter(([, v]) => v > 0).map(([k, v]) => ({ label: k, value: v, color: AUD_GRAV[k].cor }));
  const donut = segs.length
    ? donutSVG(segs, { size: 150, stroke: 22, centerTop: audNum(tot), centerSub: 'OCORRÊNCIAS' })
    : donutSVG([{ label: '', value: 1, color: '#d9f2e7' }], { size: 150, stroke: 22, centerTop: '0', centerSub: 'OCORRÊNCIAS' });
  const leg = Object.entries(porGrav).map(([k, v]) =>
    `<div><span><i style="background:${AUD_GRAV[k].cor}"></i>Gravidade ${k.toLowerCase()}</span><b>${audNum(v)}${tot ? ` <small>${pct(v / tot * 100, 0)}</small>` : ''}</b></div>`).join('');

  // base legal × consistência
  const fw = (v) => (tot ? Math.max(v / tot * 100, v ? 6 : 0) : 0).toFixed(1) + '%';
  const famBar = `<div class="aud-split">
      <div class="aud-split-bar"><b style="width:${fw(famA)};background:var(--adm)"></b><b style="width:${fw(famB)};background:#94a3b8"></b></div>
      <div class="adm-leg"><div><span><i style="background:var(--adm)"></i>Base legal (lei, Resolução, Convênio)</span><b>${audNum(famA)}</b></div>
      <div><span><i style="background:#94a3b8"></i>Regra de escrituração (Guia Prático EFD)</span><b>${audNum(famB)}</b></div></div></div>`;

  // ranking das verificações
  const maxQ = Math.max(1, ...A.map((a) => a.qtd));
  const rank = A.slice().sort((x, y) => y.qtd - x.qtd).map((a, i) =>
    `<div class="aud-rk" data-irpara="${audEsc(audId(a))}" title="Abrir o apontamento"><span>${audEsc(a.titulo)}</span>
      <div class="tr"><b style="--w:${Math.max(a.qtd / maxQ * 100, 3).toFixed(1)}%;background:${(AUD_GRAV[a.gravidade] || AUD_GRAV.Baixa).cor};animation-delay:${i * .06}s"></b></div>
      <em>${audNum(a.qtd)}</em></div>`).join('');

  const cobItens = [['Notas', cb.notas], ['Itens (C170)', cb.itens], ['Resumos (C190)', cb.c190], ['Produtos cadastrados', cb.itens_cadastrados], ['Mercadorias na lista de ST', cb.st_lista]];
  const filtros = [['todos', 'Todos', A.length], ['A', 'Base legal', A.filter((a) => a.familia === 'A').length], ['B', 'Escrituração', A.filter((a) => a.familia === 'B').length],
    ['Alta', 'Alta', A.filter((a) => a.gravidade === 'Alta').length], ['Média', 'Média', A.filter((a) => a.gravidade === 'Média').length], ['Baixa', 'Baixa', A.filter((a) => a.gravidade === 'Baixa').length]];

  el.innerHTML = `
    <div class="adm-hero aud-hero"><div>
      <small class="aud-eyebrow">Auditoria de itens do SPED Fiscal · ICMS/AM</small>
      <h2>${audEsc(cli.nome || 'Cliente')}</h2>
      <small>CNPJ ${audEsc(cli.cnpj)} · ${audEsc(cli.uf || '—')} · Período ${audEsc(cli.periodo || '—')}</small></div>
      <div class="aud-hero-r"><span class="adm-tag">Módulo Admin · teste</span>
      <span class="aud-status ${porGrav.Alta ? 'alta' : tot ? 'media' : 'ok'}">${porGrav.Alta ? 'Requer atenção' : tot ? 'Pontos a conferir' : 'Sem apontamentos'}</span></div></div>
    ${(res.avisos || []).length ? `<div class="adm-aviso"><b>Avisos da análise</b><br>${res.avisos.map(audEsc).join('<br>')}</div>` : ''}
    <div class="adm-kpis">
      <div class="adm-kpi"><span>Verificações apontadas</span><b id="audK1">0</b></div>
      <div class="adm-kpi aud-k-alta" style="animation-delay:.06s"><span>Gravidade alta</span><b id="audK2">0</b></div>
      <div class="adm-kpi laranja" style="animation-delay:.12s"><span>Total de ocorrências</span><b id="audK3">0</b></div>
      <div class="adm-kpi" style="animation-delay:.18s"><span>Valor envolvido</span><b id="audK4">R$ 0,00</b></div>
      <div class="adm-kpi verde" style="animation-delay:.24s"><span>Itens analisados</span><b id="audK5">0</b></div></div>
    <div class="adm-cols">
      <div class="adm-card"><h3>Ocorrências por gravidade</h3><div class="adm-donut-wrap"><div class="aud-donut">${donut}</div><div class="adm-leg">${leg}</div></div></div>
      <div class="adm-card"><h3>Natureza dos apontamentos</h3>${famBar}
        <div class="aud-cob">${cobItens.map(([k, v]) => `<div><b>${audNum(v)}</b><span>${k}</span></div>`).join('')}</div></div></div>
    ${A.length ? `<div class="adm-card"><h3>Ranking das verificações <span class="aud-h-sub">· clique para abrir o apontamento</span></h3><div class="aud-rank">${rank}</div></div>` : ''}
    ${audConciliacao(res.conciliacao || [])}
    <div class="adm-card"><div class="aud-lista-h"><h3>Apontamentos</h3>
      <input class="adm-input aud-busca" id="audBusca" placeholder="Buscar por título, descrição, norma ou artigo…" value="${audEsc(AUDAM.busca)}"></div>
      <div class="adm-chips" style="margin-bottom:8px">${filtros.map(([k, t, n]) => `<span class="adm-chip${AUDAM.filtro === k ? ' on' : ''}" data-audfiltro="${audEsc(k)}">${t} <b>${n}</b></span>`).join('')}</div>
      <div id="audLista">${audLista()}</div></div>
    ${(res.fontes || []).length ? `<div class="adm-card"><h3>Normas consultadas <span class="aud-h-sub">· textos oficiais lidos em ${audEsc(res.lido_em || '')}</span></h3><div class="aud-fontes">${[...new Map(res.fontes.map((f) => [f.ref.split(',')[0], f])).values()].map((f) => `<a href="${audEsc(f.url)}" target="_blank" rel="noopener">${audEsc(f.ref.split(',')[0])} ↗</a>`).join('')}</div></div>` : ''}
    <div class="adm-rodape">Hipóteses para o contador conferir. Cada apontamento transcreve o dispositivo lido no site oficial (SEFAZ-AM, CONFAZ, Senado/Planalto, Sped) e mostra, ocorrência por ocorrência, o que a norma exige e o que o arquivo traz. Benefícios e reduções de base ainda não são cruzados.</div>`;
  el.hidden = false;
  animateArcs(el);
  admContar($('#audK1'), A.length, false); admContar($('#audK2'), porGrav.Alta, false); admContar($('#audK3'), tot, false);
  admContar($('#audK4'), valor, true); admContar($('#audK5'), cb.itens || 0, false);
}

// Relatório HTML autônomo: o mesmo painel, com todos os apontamentos abertos, CSS embutido e sem depender do app.
async function audHtmlRelatorio() {
  const res = AUDAM.res;
  const tmp = document.createElement('div');
  tmp.innerHTML = $('#audPainel').innerHTML;
  const salvo = { filtro: AUDAM.filtro, busca: AUDAM.busca, aberta: AUDAM.aberta };
  AUDAM.filtro = 'todos'; AUDAM.busca = '';
  const lista = $('#audLista', tmp);
  if (lista) lista.innerHTML = audLista();
  Object.assign(AUDAM, salvo);
  $$('.aud-op', tmp).forEach((o) => o.classList.add('aberta'));
  $$('details', tmp).forEach((d) => d.setAttribute('open', ''));
  $$('.aud-busca, .adm-chips, .aud-h-sub', tmp).forEach((n) => { if (!/textos oficiais/.test(n.textContent)) n.remove(); });
  $$('[data-irpara]', tmp).forEach((n) => { n.removeAttribute('data-irpara'); n.removeAttribute('title'); });
  // números finais dos indicadores (no app eles sobem animados)
  const A = res.achados || [];
  const fim = {
    audK1: audNum(A.length), audK2: audNum(A.filter((a) => a.gravidade === 'Alta').reduce((x, a) => x + a.qtd, 0)),
    audK3: audNum(A.reduce((x, a) => x + a.qtd, 0)), audK4: brl(A.reduce((x, a) => x + (a.valor || 0), 0)),
    audK5: audNum((res.cobertura || {}).itens || 0),
  };
  Object.entries(fim).forEach(([id, v]) => { const n = $('#' + id, tmp); if (n) n.textContent = v; });
  $$('.arc', tmp).forEach((c) => (c.style.strokeDashoffset = '0'));
  let css = [...document.styleSheets].map((ss) => { try { return [...ss.cssRules].map((r) => r.cssText).join('\n'); } catch (_) { return ''; } }).join('\n');
  if (css.length < 2000) { try { css = await (await fetch('styles.css')).text(); } catch (_) {} }
  const cli = res.cliente || {};
  const agora = new Date();
  const quando = agora.toLocaleDateString('pt-BR') + ' ' + agora.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  const arqs = AUDAM.sped.map((p) => audEsc(p.split(/[\\/]/).pop())).join(', ');
  return `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auditoria ICMS/AM — ${audEsc(cli.nome || '')} — ${audEsc(cli.periodo || '')}</title>
<style>${css}
body{display:block;height:auto;min-height:100%;padding:24px 16px 40px}
.aud-rel{max-width:1240px;margin:0 auto}
#audPainel{margin-top:0}
.aud-rel-meta{color:var(--ink2);font-size:12px;margin:0 0 12px}
.aud-op .adm-op-h{cursor:pointer}
@media print{body{padding:0;background:#fff}.adm-card,.adm-kpi{box-shadow:none;border:1px solid var(--line)}.aud-op,.adm-card{break-inside:avoid}
  *{animation:none!important;transition:none!important}.aud-rk .tr b,.aud-bar .tr b{width:var(--w)!important}.adm-det{display:block!important}}
</style></head><body><div class="aud-rel">
<p class="aud-rel-meta">Relatório gerado em ${audEsc(quando)} · Arquivo(s): ${arqs}</p>
<div id="audPainel">${tmp.innerHTML}</div></div>
<script>document.addEventListener('click',function(e){var h=e.target.closest('[data-abrirauda]');if(h&&!e.target.closest('a'))h.parentElement.classList.toggle('aberta');});</script>
</body></html>`;
}

function audSelecao() {
  const el = $('#audSel');
  el.hidden = !AUDAM.sped.length;
  el.innerHTML = AUDAM.sped.map((p) => `<span>SPED · ${audEsc(p.split(/[\\/]/).pop())}</span>`).join('');
  $('#btnAudRodar').disabled = !AUDAM.sped.length;
}

function audInit() {
  const adm = window.fiscocont && window.fiscocont.admin;
  if (!adm || !$('#btnAudSped')) return;
  $('#btnAudSped').addEventListener('click', async () => {
    const r = await adm.audPick();
    if (!r || r.canceled || !r.paths) return;
    AUDAM.sped = r.paths; $('#btnAudSped').classList.add('ok'); audSelecao();
  });
  $('#btnAudRodar').addEventListener('click', async () => {
    overlay(true, 'Auditando os itens do SPED Fiscal…');
    try {
      const r = await adm.audAnalisar({ sped: AUDAM.sped });
      overlay(false);
      if (!r || r.error) { toast((r && r.error) || 'Falha na auditoria.', true); return; }
      Object.assign(AUDAM, { res: r.res, filtro: 'todos', busca: '', aberta: null });
      $('#audVazio').hidden = true; audRender();
      $('#btnAudHtml').disabled = false;
    } catch (e) { overlay(false); toast('Falha: ' + e.message, true); }
  });
  $('#btnAudHtml').addEventListener('click', async () => {
    if (!AUDAM.res) return;
    try {
      const r = await window.fiscocont.fiscal.nfseExportarHtml(await audHtmlRelatorio(), 'auditoria-am', (AUDAM.res.cliente || {}).nome || '');
      if (!r || r.canceled) return;
      if (r.error) { toast(r.error, true); return; }
      toast('Auditoria exportada.');
      window.fiscocont.openPath(r.path);
    } catch (e) { toast('Falha ao exportar: ' + e.message, true); }
  });
  const painel = $('#audPainel');
  painel.addEventListener('click', (ev) => {
    const h = ev.target.closest('[data-abrirauda]');
    if (h) {
      const id = h.dataset.abrirauda;
      AUDAM.aberta = AUDAM.aberta === id ? null : id;
      $$('.aud-op', painel).forEach((o) => o.classList.toggle('aberta', o.dataset.audid === AUDAM.aberta));
      return;
    }
    const fl = ev.target.closest('[data-audfiltro]');
    if (fl) {
      AUDAM.filtro = fl.dataset.audfiltro;
      $$('[data-audfiltro]', painel).forEach((c) => c.classList.toggle('on', c === fl));
      $('#audLista').innerHTML = audLista();
      return;
    }
    const rk = ev.target.closest('[data-irpara]');
    if (rk) {
      AUDAM.filtro = 'todos'; AUDAM.busca = ''; AUDAM.aberta = rk.dataset.irpara;
      $$('[data-audfiltro]', painel).forEach((c) => c.classList.toggle('on', c.dataset.audfiltro === 'todos'));
      $('#audBusca').value = '';
      $('#audLista').innerHTML = audLista();
      const alvo = $$('.aud-op', painel).find((o) => o.dataset.audid === AUDAM.aberta);
      if (alvo) alvo.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
  painel.addEventListener('input', (ev) => {
    if (ev.target.id !== 'audBusca') return;
    AUDAM.busca = ev.target.value;
    $('#audLista').innerHTML = audLista();
  });
}

// ------------------------------------------------------------------ Evolução Tributária (Admin)
const EVO = { sped: [], res: null };
function evoOpcoes(cliente) {
  return { escritorio: ($('#evoEscritorio').value || '').trim() || 'Liddera | Inteligência em Negócios',
    recado: $('#evoRecado').value || '', cliente };
}
function evoRender() {
  const el = $('#evoPainel');
  if (!EVO.res || !window.EvoDash) { el.hidden = true; return; }
  window.EvoDash.render(el, EVO.res, evoOpcoes(false));
  el.hidden = false;
}
async function evoHtmlCliente() {
  const a = await window.fiscocont.admin.evoAssets();
  if (!a || a.error || !a.css || !a.js) throw new Error((a && a.error) || 'arquivos do painel ausentes.');
  const css = a.css, js = a.js;
  const d = EVO.res, e = d.empresa || {}, p = d.periodo || {};
  const dados = JSON.stringify(d).replace(/</g, '\\u003c');
  const op = JSON.stringify(evoOpcoes(true)).replace(/</g, '\\u003c');
  return `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evolução Tributária · ${audEsc(e.nome || '')} · ${audEsc(p.ini_rot || '')} a ${audEsc(p.fim_rot || '')}</title>
<style>body{margin:0;background:#f4f6fb}.evo-pg{max-width:1180px;margin:0 auto;padding:24px 16px 32px}@page{size:A4;margin:10mm}@media print{body{background:#fff}.evo-pg{padding:0}}
${css}</style></head><body><div class="evo-pg" id="evo"></div>
<script>${js}</script>
<script>EvoDash.render(document.getElementById('evo'), ${dados}, ${op});</script>
</body></html>`;
}
function evoInit() {
  const adm = window.fiscocont && window.fiscocont.admin;
  if (!adm || !$('#btnEvoSped')) return;
  $('#btnEvoSped').addEventListener('click', async () => {
    const r = await adm.evoPick();
    if (!r || r.canceled || !r.paths) { if (r && r.error) toast(r.error, true); return; }
    EVO.sped = r.paths;
    $('#btnEvoSped').classList.add('ok');
    const sel = $('#evoSel');
    sel.hidden = false;
    sel.innerHTML = `<span><b>${EVO.sped.length}</b> arquivo(s)</span>` + EVO.sped.slice(0, 14).map((p) => `<span>${audEsc(p.split(/[\\/]/).pop())}</span>`).join('') +
      (EVO.sped.length > 14 ? `<span>+ ${EVO.sped.length - 14}</span>` : '');
    $('#btnEvoRodar').disabled = false;
  });
  $('#btnEvoOpcoes').addEventListener('click', () => { $('#evoOpcoes').hidden = !$('#evoOpcoes').hidden; });
  ['#evoEscritorio', '#evoRecado'].forEach((id) => $(id).addEventListener('change', () => { if (EVO.res) evoRender(); }));
  $('#btnEvoRodar').addEventListener('click', async () => {
    overlay(true, `Lendo ${EVO.sped.length} SPED Fiscal(is)…`);
    try {
      const r = await adm.evoAnalisar({ sped: EVO.sped });
      overlay(false);
      if (!r || r.error) { toast((r && r.error) || 'Falha na análise.', true); return; }
      EVO.res = r.res;
      $('#evoVazio').hidden = true;
      $('#btnEvoHtml').disabled = false;
      evoRender();
    } catch (e) { overlay(false); toast('Falha: ' + e.message, true); }
  });
  $('#btnEvoHtml').addEventListener('click', async () => {
    if (!EVO.res) return;
    try {
      const r = await window.fiscocont.fiscal.nfseExportarHtml(await evoHtmlCliente(), 'evolucao', (EVO.res.empresa || {}).nome || '');
      if (!r || r.canceled) return;
      if (r.error) { toast(r.error, true); return; }
      toast('Relatório do cliente exportado.');
      window.fiscocont.openPath(r.path);
    } catch (e) { toast('Falha ao exportar: ' + e.message, true); }
  });
}

// ------------------------------------------------------------------ Radar
function radarChave(o) { return `${ADM.radar.res.cliente.cnpj}|${o.tipo}|${o.titulo}`; }
function radarEstado(o) { return (ADM.radar.status[radarChave(o)] || {}).status || 'nova'; }

function radarSelecao() {
  const r = ADM.radar, el = $('#radarSel');
  const pecas = [];
  r.efdc.forEach((p) => pecas.push('EFD-C · ' + admNome(p)));
  r.fiscal.forEach((p) => pecas.push('ICMS/IPI · ' + admNome(p)));
  r.xml.forEach((p) => pecas.push('XML · ' + admNome(p)));
  el.hidden = !pecas.length;
  el.innerHTML = pecas.map((t) => `<span>${esc(t)}</span>`).join('');
  $('#btnRadarRodar').disabled = !r.efdc.length;
}

function radarTabela(o) {
  const ev = o.evidencias || [];
  if (!ev.length) return '';
  let cab, lin;
  if (o.tipo === 'monofasico') {
    cab = ['Nota', 'Data', 'Produto', 'NCM', 'CST', 'PIS+COFINS'];
    lin = ev.map((e) => [e.nota, e.data, e.produto, e.ncm, e.cst, brl(e.valor)]);
  } else if (o.tipo === 'tema69') {
    cab = ['Nota', 'Data', 'Produto', 'ICMS destacado', 'PIS+COFINS a mais'];
    lin = ev.map((e) => [e.nota, e.data, e.produto, brl(e.icms), brl(e.valor)]);
  } else {
    cab = ['Competência', 'Nota', 'Data', 'Produto', 'CFOP', 'ICMS'];
    lin = ev.map((e) => [e.competencia, e.nota, e.data, e.produto, e.cfop, brl(e.icms)]);
  }
  return `<table class="adm-tab"><thead><tr>${cab.map((c) => `<th>${c}</th>`).join('')}</tr></thead><tbody>${
    lin.map((l) => `<tr>${l.map((c) => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>
    <div style="font-size:11.5px;color:var(--ink2);margin-top:4px">Mostrando até ${ev.length} exemplos. A lista completa sai da própria EFD.</div>`;
}

function radarDetalhe(o) {
  const L = ADM.radar.res.legal[o.tipo];
  const fn = L.fundamento.map((f) => `<div class="fn"><b>${esc(f.norma)}</b><span class="fonte">${esc(f.fonte)}</span><br>${esc(f.texto)}</div>`).join('');
  const aten = [...L.atencao, ...(o.tipo === 'monofasico' ? [] : [])].map((a) => `<li>${esc(a)}</li>`).join('');
  const est = radarEstado(o);
  const k = escA(radarChave(o));
  return `<div class="adm-det">
    <div style="font-size:12.5px;color:var(--ink2);margin:2px 0 4px">${esc(o.resumo)}</div>
    <div class="adm-lg"><b class="t">Fundamento legal</b>${fn}</div>
    <div class="adm-lg"><b class="t">Como o sistema apurou</b>${esc(o.como)}</div>
    <div class="adm-lg"><b class="t">Prazo e forma de recuperar</b>${esc(L.prazo)}</div>
    <div class="adm-lg at"><b class="t">Pontos de atenção</b><ul>${aten}</ul></div>
    <div class="adm-lg" style="background:transparent;border-left-color:var(--line);color:inherit"><b class="t">Exemplos nos arquivos</b>${radarTabela(o)}</div>
    <div class="adm-acoes">
      ${est !== 'validada' ? `<button class="p" data-st="validada" data-k="${k}">Marcar como validada</button>` : ''}
      ${est !== 'descartada' ? `<button data-st="descartada" data-k="${k}">Descartar</button>` : ''}
      ${est !== 'nova' ? `<button data-st="nova" data-k="${k}">Reabrir</button>` : ''}
    </div></div>`;
}

function radarRender() {
  const R = ADM.radar, res = R.res, el = $('#radarPainel');
  const ops = res.oportunidades;
  if (!ops.length) {
    el.innerHTML = `<div class="adm-hero"><div><h2>${esc(res.cliente.nome || 'Cliente')}</h2><small>Nenhuma oportunidade encontrada nos arquivos analisados</small></div></div>
      ${(res.cobertura || []).length ? `<div class="adm-card"><h3>O que foi analisado</h3><div style="font-size:13px;line-height:1.6">${res.cobertura.map((t) => '• ' + esc(t)).join('<br>')}</div></div>` : ''}
      ${res.avisos.length ? `<div class="adm-aviso">${res.avisos.map(esc).join('<br>')}</div>` : ''}`;
    el.hidden = false; return;
  }
  const tipos = ['Todos', ...new Set(ops.map((o) => o.tipo))];
  const vis = ops.filter((o) => R.filtro === 'Todos' || o.tipo === R.filtro);
  const tot = vis.reduce((a, o) => a + o.valor, 0);
  const val = vis.filter((o) => radarEstado(o) === 'validada').reduce((a, o) => a + o.valor, 0);
  const desc = vis.filter((o) => radarEstado(o) === 'descartada').reduce((a, o) => a + o.valor, 0);
  const aval = tot - val - desc;
  const porTipo = {};
  ops.forEach((o) => { porTipo[o.tipo] = (porTipo[o.tipo] || 0) + o.valor; });
  const totalGeral = ops.reduce((a, o) => a + o.valor, 0);
  let acc = 0;
  const fatias = Object.entries(porTipo).map(([t, v]) => { const a = acc, b = acc + v / totalGeral * 100; acc = b; return `${ADM_COR[t]} ${a}% ${b}%`; });
  const leg = Object.entries(porTipo).map(([t, v]) => `<div><span><i style="background:${ADM_COR[t]}"></i>${ADM_TIPO[t]}</span><b>${brl(v)}</b></div>`).join('');
  const w = (v) => (tot ? Math.max(v / tot * 100, v > 0 ? 14 : 0) : 0);
  const fun = [['Identificado', tot, '#8a7bd6'], ['A validar', aval, '#e8601c'], ['Validado', val, '#12a37a'], ['Descartado', desc, '#9aa3b8']]
    .map(([n, v, c], i) => `<div class="l"><span>${n}</span><div class="tr"><b class="${v > 0 ? 'v' : ''}" style="--w:${w(v)}%;background:${c};animation-delay:${i * .12}s">${v > 0 ? brl(v) : ''}</b></div></div>`).join('');
  const lista = vis.map((o, i) => {
    const est = radarEstado(o), ab = R.aberta === radarChave(o);
    const confCls = { Alta: 'ok', 'Média': 'av', Baixa: 'no' }[o.confianca] || 'na';
    const estPill = est === 'validada' ? '<span class="adm-pill ok">Validada</span>' : est === 'descartada' ? '<span class="adm-pill na">Descartada</span>' : '';
    return `<div class="adm-op${ab ? ' aberta' : ''}" style="animation:admUp .4s ease both;animation-delay:${i * .06}s">
      <div class="adm-op-h" data-abrir="${escA(radarChave(o))}"><div><b>${esc(o.titulo)}</b>
        <small>${esc(o.periodos.map(admMes).join(', '))}
          <span class="adm-pill ${confCls}">Confiança ${esc(o.confianca.toLowerCase())}</span>
          <span class="adm-pill ${o.base_legal_status === 'conferida' ? 'ok' : 'rx'}">${o.base_legal_status === 'conferida' ? 'Base legal conferida' : 'Revalidar norma estadual'}</span>${estPill}</small></div>
        <div class="adm-val">${brl(o.valor)}</div></div>${radarDetalhe(o)}</div>`;
  }).join('');
  const soon = res.em_desenvolvimento.map((d) => `<div><b>${esc(d.titulo)}</b><br>${esc(d.norma)}<br><span style="color:var(--ink2)">${esc(d.texto)}</span></div>`).join('');
  el.innerHTML = `
    <div class="adm-hero"><div><h2>${esc(res.cliente.nome || 'Cliente')}</h2>
      <small>CNPJ ${esc(res.cliente.cnpj)} · ${esc(res.periodos.map(admMes).join(', '))} · ${res.arquivos_efdc} EFD-Contribuições${res.arquivos_fiscal ? ' + ' + res.arquivos_fiscal + ' EFD ICMS/IPI' : ''}</small></div>
      <span class="adm-tag">Módulo Admin · teste</span></div>
    <div class="adm-kpis">
      <div class="adm-kpi"><span>Potencial identificado</span><b id="radK1">R$ 0,00</b></div>
      <div class="adm-kpi laranja" style="animation-delay:.08s"><span>A validar</span><b id="radK2">R$ 0,00</b></div>
      <div class="adm-kpi verde" style="animation-delay:.16s"><span>Validado</span><b id="radK3">R$ 0,00</b></div>
      <div class="adm-kpi" style="animation-delay:.24s"><span>Oportunidades</span><b id="radK4">0</b></div></div>
    <div class="adm-cols">
      <div class="adm-card"><h3>Potencial por tipo</h3><div class="adm-donut-wrap"><div class="adm-donut" style="background:conic-gradient(${fatias.join(',')})"></div><div class="adm-leg">${leg}</div></div></div>
      <div class="adm-card"><h3>Do achado à validação</h3><div class="adm-fun">${fun}</div></div></div>
    <div class="adm-card"><h3>Oportunidades <span style="font-weight:400;color:var(--ink2);font-size:12px">· clique para ver base legal, cálculo, prazo e exemplos</span></h3>
      <div class="adm-chips" style="margin-bottom:8px">${tipos.map((t) => `<span class="adm-chip${R.filtro === t ? ' on' : ''}" data-filtro="${t}">${t === 'Todos' ? 'Todos' : ADM_TIPO[t]}</span>`).join('')}</div>
      ${lista}</div>
    ${(res.cobertura || []).length ? `<div class="adm-card"><h3>O que foi analisado</h3><div style="font-size:13px;line-height:1.6">${res.cobertura.map((t) => '• ' + esc(t)).join('<br>')}</div></div>` : ''}
    ${res.avisos.length ? `<div class="adm-aviso"><b>Avisos da análise</b><br>${res.avisos.map(esc).join('<br>')}</div>` : ''}
    <div class="adm-card"><h3>Próximas verificações (ainda não implementadas)</h3><div class="adm-soon">${soon}</div></div>
    <div class="adm-rodape">Hipóteses para análise do contador. A base legal deve ser revalidada, e o histórico do cliente conferido (ações, compensações já feitas), antes de qualquer proposta ou pedido.</div>`;
  el.hidden = false;
  admContar($('#radK1'), tot, true); admContar($('#radK2'), aval, true); admContar($('#radK3'), val, true); admContar($('#radK4'), vis.length, false);
}

// ------------------------------------------------------------------ Legalização
const LEG_STATUS = [['nao_verificado', 'Não verificado'], ['regular', 'Regular'], ['irregular', 'Irregular'], ['nao_aplica', 'Não se aplica']];
const LEG_NIVEL = { ok: ['ok', 'Em dia'], atencao: ['av', 'Atenção'], critico: ['no', 'Crítico'], pendente: ['na', 'A verificar'], nao_aplica: ['na', 'Não se aplica'] };

function legalRender() {
  const L = ADM.legal, r = L.res, el = $('#legalPainel');
  const off = 314 * (1 - r.indice / 100);
  const cont = r.contagem;
  const alertas = r.alertas.map((a) => `<div class="adm-aviso" style="${a.nivel === 'critico' ? 'background:#fdecec;color:#8a1f1f' : ''}">${esc(a.texto)}</div>`).join('');
  const dados = r.dados.map((d) => `<span>${esc(d.rotulo)}</span><span>${esc(d.valor)}</span>`).join('');
  const cnaes = `<div style="font-size:12.5px;line-height:1.7"><b>${esc(r.cnae_principal.codigo)}</b> ${esc(r.cnae_principal.descricao)} <span class="adm-pill rx">principal</span>${
    r.cnaes_secundarios.map((c) => `<br>${esc(c.codigo)} ${esc(c.descricao)}`).join('')}</div>`;
  const qsa = r.qsa.length ? `<div class="adm-kv">${r.qsa.map((q) => `<span>${esc(q.qualificacao)}</span><span>${esc(q.nome)}${q.entrada ? ' · desde ' + esc(q.entrada) : ''}</span>`).join('')}</div>` : '<div style="color:var(--ink2);font-size:12.5px">Sem dados de sócios.</div>';
  let grupo = null, chk = `<div class="adm-chk h"><span>Item</span><span>Status</span><span>Validade</span><span>Observação</span><span>Situação</span></div>`;
  r.itens.forEach((it) => {
    if (it.grupo !== grupo) { grupo = it.grupo; chk += `<div class="adm-grp">${esc(grupo)}</div>`; }
    const [cls, nome] = LEG_NIVEL[it.nivel];
    const sel = LEG_STATUS.map(([v, n]) => `<option value="${v}"${it.status === v ? ' selected' : ''}>${n}</option>`).join('');
    chk += `<div class="adm-chk"><span>${esc(it.nome)}<small>${esc(it.orgao)}${it.dica ? ' · ' + esc(it.dica) : ''}</small></span>
      <select data-id="${it.id}" data-f="status">${sel}</select>
      ${it.tem_validade ? `<input type="date" data-id="${it.id}" data-f="validade" value="${escA(it.validade)}">` : '<span style="color:var(--ink2)">—</span>'}
      <input type="text" data-id="${it.id}" data-f="obs" value="${escA(it.obs)}" placeholder="Anotação">
      <span><span class="adm-pill ${cls}" title="${nome}">${esc(it.rotulo)}</span></span></div>`;
  });
  const plano = r.plano.length ? r.plano.map((p, i) => `<div class="${p.nivel}" style="animation-delay:${i * .05}s"><span class="n">${i + 1}.</span><span><b>${esc(p.item)}</b> · ${esc(p.rotulo)}${p.dica ? '<br><small style="color:var(--ink2)">' + esc(p.dica) + '</small>' : ''}</span><span class="adm-pill ${LEG_NIVEL[p.nivel][0]}">${LEG_NIVEL[p.nivel][1]}</span></div>`).join('') : '<div class="atencao" style="background:#e8f6f0">Nenhuma pendência.</div>';
  el.innerHTML = `
    <div class="adm-hero"><div><h2>${esc(r.razao_social)}</h2><small>CNPJ ${esc(r.cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5'))} · situação ${esc(r.situacao || '—')} · ${esc(r.regime)}</small></div>
      <span class="adm-tag">Módulo Admin · teste</span></div>
    <div class="adm-card"><div class="adm-score">
      <div class="adm-ring"><svg viewBox="0 0 120 120"><circle class="bg" cx="60" cy="60" r="50" fill="none" stroke-width="12"/><circle class="fg" cx="60" cy="60" r="50" fill="none" stroke-width="12" style="--o:${off}"/></svg>
        <div class="n"><span id="legIdx">0</span><small>de 100</small></div></div>
      <div><h3 style="margin:0 0 8px">Índice de regularidade</h3>
        <div class="adm-cont"><div class="c1"><b>${cont.critico}</b><span>Críticos</span></div><div class="c2"><b>${cont.atencao}</b><span>Atenção</span></div><div class="c3"><b>${cont.pendente}</b><span>A verificar</span></div><div class="c4"><b>${cont.ok}</b><span>Em dia</span></div></div></div></div>
      ${alertas ? `<div style="display:grid;gap:6px;margin-top:10px">${alertas}</div>` : ''}</div>
    <div class="adm-card"><h3>Plano de ação (por urgência)</h3><div class="adm-plano">${plano}</div></div>
    <div class="adm-cols"><div class="adm-card"><h3>Dados cadastrais · Receita Federal (automático)</h3><div class="adm-kv">${dados}</div></div>
      <div class="adm-card"><h3>Atividades (CNAE) e sócios</h3>${cnaes}<h3 style="margin-top:12px">Quadro societário</h3>${qsa}</div></div>
    <div class="adm-card"><h3>Licenças, certidões e acessos <span style="font-weight:400;color:var(--ink2);font-size:12px">· preenchido pelo analista; a lista segue as atividades da empresa</span></h3>${chk}
      <div style="font-size:11.5px;color:var(--ink2);margin-top:8px">A lista de licenças por atividade é uma referência do que costuma ser exigido. A exigência real é definida pela prefeitura, pelo Corpo de Bombeiros, pela vigilância, pelo órgão ambiental e demais órgãos competentes.</div></div>`;
  el.hidden = false;
  admContar($('#legIdx'), r.indice, false);
  $('#btnLegalPdf').disabled = false;
  $('#legalVazio').hidden = true;
}

function legalSujo(v) {
  ADM.legal.sujo = v;
  $('#legalSujo').hidden = !v;
  $('#btnLegalSalvar').disabled = !v;
}

async function legalRecentes() {
  const r = await window.fiscocont.admin.legalLista();
  const sel = $('#legalRecentes');
  if (!r || !r.ok) return;
  sel.innerHTML = '<option value="">Consultadas recentemente…</option>' + r.lista.map((c) => `<option value="${escA(c.cnpj)}">${esc(c.nome)}</option>`).join('');
}

async function legalConsultar(cnpj, cache) {
  overlay(true, cache ? 'Abrindo levantamento…' : 'Consultando o CNPJ na Receita…');
  try {
    const r = await window.fiscocont.admin.legalConsultar({ cnpj, usarCache: !!cache });
    overlay(false);
    if (!r || r.error) { toast((r && r.error) || 'Falha na consulta.', true); return; }
    ADM.legal.cnpj = r.res.cnpj; ADM.legal.res = r.res; ADM.legal.itens = r.itens || {};
    $('#legalCnpj').value = r.res.cnpj;
    legalSujo(false); legalRender(); legalRecentes();
  } catch (e) { overlay(false); toast('Falha: ' + e.message, true); }
}

// ------------------------------------------------------------------ ligações
function initAdminModulos() {
  audInit();
  evoInit();
  const adm = window.fiscocont && window.fiscocont.admin;
  if (!adm) return;
  // Radar
  const pick = (tipo, btn) => async () => {
    const r = await adm.radarPick(tipo);
    if (!r || r.canceled || !r.paths) return;
    if (tipo === 'xml' || tipo === 'xmlpasta') {
      // soma às seleções anteriores (zips de meses diferentes, pastas e arquivos avulsos)
      ADM.radar.xml = [...new Set([...(ADM.radar.xml || []), ...r.paths])];
    } else {
      ADM.radar[tipo === 'fiscal' ? 'fiscal' : 'efdc'] = r.paths;
    }
    btn.classList.add('ok');
    radarSelecao();
  };
  $('#btnRadarEfdc').addEventListener('click', pick('efdc', $('#btnRadarEfdc')));
  $('#btnRadarFiscal').addEventListener('click', pick('fiscal', $('#btnRadarFiscal')));
  $('#btnRadarXml').addEventListener('click', pick('xml', $('#btnRadarXml')));
  $('#btnRadarXmlPasta').addEventListener('click', pick('xmlpasta', $('#btnRadarXmlPasta')));
  $('#btnRadarRodar').addEventListener('click', async () => {
    overlay(true, (ADM.radar.xml && ADM.radar.xml.length) ? 'Lendo as EFD e os XMLs. Com muitos XMLs isso pode levar alguns minutos…' : 'Procurando oportunidades nos arquivos…');
    try {
      const r = await adm.radarAnalisar({ efdc: ADM.radar.efdc, fiscal: ADM.radar.fiscal, xml: ADM.radar.xml });
      overlay(false);
      if (!r || r.error) { toast((r && r.error) || 'Falha na análise.', true); return; }
      ADM.radar.res = r.res; ADM.radar.status = r.status || {}; ADM.radar.filtro = 'Todos'; ADM.radar.aberta = null;
      $('#radarVazio').hidden = true;
      radarRender();
    } catch (e) { overlay(false); toast('Falha: ' + e.message, true); }
  });
  $('#radarPainel').addEventListener('click', async (ev) => {
    const f = ev.target.closest('[data-filtro]');
    if (f) { ADM.radar.filtro = f.dataset.filtro; radarRender(); return; }
    const b = ev.target.closest('button[data-st]');
    if (b) {
      const r = await adm.radarStatus({ chave: b.dataset.k, status: b.dataset.st });
      if (r && r.ok) { ADM.radar.status = r.status; radarRender(); toast(b.dataset.st === 'validada' ? 'Marcada como validada.' : b.dataset.st === 'descartada' ? 'Oportunidade descartada.' : 'Reaberta.'); }
      return;
    }
    const h = ev.target.closest('[data-abrir]');
    if (h) {
      const op = h.parentElement, abrir = !op.classList.contains('aberta');
      $$('#radarPainel .adm-op').forEach((x) => x.classList.remove('aberta'));
      if (abrir) op.classList.add('aberta');
      ADM.radar.aberta = abrir ? h.dataset.abrir : null;
    }
  });
  // Legalização
  $('#btnLegalConsultar').addEventListener('click', () => legalConsultar($('#legalCnpj').value, false));
  $('#legalCnpj').addEventListener('keydown', (e) => { if (e.key === 'Enter') legalConsultar($('#legalCnpj').value, false); });
  $('#legalRecentes').addEventListener('change', (e) => { if (e.target.value) legalConsultar(e.target.value, true); });
  $('#legalPainel').addEventListener('input', (ev) => {
    const t = ev.target;
    if (!t.dataset || !t.dataset.id) return;
    const it = (ADM.legal.itens[t.dataset.id] = ADM.legal.itens[t.dataset.id] || {});
    it[t.dataset.f] = t.value;
    legalSujo(true);
  });
  $('#btnLegalSalvar').addEventListener('click', async () => {
    overlay(true, 'Salvando e recalculando…');
    const r = await adm.legalSalvar({ cnpj: ADM.legal.cnpj, itens: ADM.legal.itens });
    overlay(false);
    if (!r || r.error) { toast((r && r.error) || 'Falha ao salvar.', true); return; }
    ADM.legal.res = r.res; ADM.legal.itens = r.itens || {};
    legalSujo(false); legalRender(); toast('Levantamento salvo.');
  });
  $('#btnLegalPdf').addEventListener('click', async () => {
    overlay(true, 'Preparando o PDF…');
    const r = await adm.legalSalvar({ cnpj: ADM.legal.cnpj, itens: ADM.legal.itens, html: true });
    overlay(false);
    if (!r || r.error || !r.html) { toast((r && r.error) || 'Falha ao gerar o PDF.', true); return; }
    ADM.legal.res = r.res; legalSujo(false); legalRender();
    const out = await window.fiscocont.fiscal.efdClientePdf({ htmlEstatico: r.html, nomeSugerido: 'Levantamento-' + (r.res.razao_social || ADM.legal.cnpj) });
    if (out && out.ok) toast('PDF salvo.');
    else if (out && out.error) toast(out.error, true);
  });
  legalRecentes();
}

/* Evolução Tributária e de Faturamento — painel de gráficos.
 * Arquivo autônomo (sem dependência do app): o mesmo código desenha a tela do sistema
 * e vai embutido no HTML enviado ao cliente, por isso tudo aqui é JS puro + SVG.
 * Uso: EvoDash.render(elemento, dados, { escritorio, recado, tecnico, cliente })
 */
(function (g) {
  'use strict';
  var COR = {
    fat: '#4a3aa7', dev: '#c3c8d6', compras: '#8a93a8',
    icms: '#2a78d6', deb_esp: '#eb6834', st: '#1baf7a', difal: '#eda100', fcp: '#e87ba4', ipi: '#008300',
    carga: '#1f2a5a', ant_rec: '#eb6834', ant_cred: '#2a78d6',
  };
  var NF = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function brl(v) { return (v < 0 ? '-R$ ' : 'R$ ') + NF.format(Math.abs(v || 0)); }
  function pct(v, d) { return v == null ? '—' : new Intl.NumberFormat('pt-BR', { minimumFractionDigits: d == null ? 2 : d, maximumFractionDigits: d == null ? 2 : d }).format(v) + '%'; }
  function compacto(v) {
    var a = Math.abs(v || 0), s = v < 0 ? '-' : '';
    if (a >= 1e9) return s + 'R$ ' + (a / 1e9).toFixed(1).replace('.', ',') + ' bi';
    if (a >= 1e6) return s + 'R$ ' + (a / 1e6).toFixed(1).replace('.', ',') + ' mi';
    if (a >= 1e4) return s + 'R$ ' + Math.round(a / 1e3) + ' mil';
    if (a >= 1e3) return s + 'R$ ' + (Math.round(a / 100) / 10).toString().replace('.', ',') + ' mil';
    return s + 'R$ ' + Math.round(a);
  }
  function esc(x) { return String(x == null ? '' : x).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function soma(a) { return a.reduce(function (x, y) { return x + (y || 0); }, 0); }
  function niceMax(v) {
    if (v <= 0) return 1;
    var e = Math.pow(10, Math.floor(Math.log10(v))), f = v / e;
    var passos = [1, 1.2, 1.6, 2, 2.4, 3, 4, 5, 6, 8, 10];   // múltiplos de 4 divisões "redondas"
    for (var i = 0; i < passos.length; i++) if (f <= passos[i]) return passos[i] * e;
    return 10 * e;
  }

  var TIPS = {};      // tooltips por gráfico
  var seq = 0;

  /* ---------------- barras (simples ou empilhadas) + linha opcional na MESMA escala */
  function barras(meses, series, o) {
    o = o || {};
    var id = 'evc' + (++seq), W = 900, H = o.h || 270, L = 64, Rr = 12, T = 14, B = 34;
    var n = meses.length, pw = W - L - Rr, ph = H - T - B;
    var tot = meses.map(function (_, i) { return soma(series.map(function (s) { return s.valores[i]; })); });
    var maxv = niceMax(Math.max.apply(null, tot.concat(o.linha ? o.linha.valores : []).concat([0])) * 1.04);
    var y = function (v) { return T + ph - (v / maxv) * ph; };
    var slot = pw / n, bw = Math.max(6, Math.min(46, slot * 0.62));
    var out = '';
    for (var k = 0; k <= 4; k++) {
      var gv = maxv * k / 4, gy = y(gv);
      out += '<line x1="' + L + '" x2="' + (W - Rr) + '" y1="' + gy + '" y2="' + gy + '" class="evo-grid"/>' +
        '<text x="' + (L - 8) + '" y="' + (gy + 4) + '" class="evo-ax" text-anchor="end">' + esc(compacto(gv)) + '</text>';
    }
    var passo = n > 18 ? 3 : n > 12 ? 2 : 1;
    TIPS[id] = [];
    meses.forEach(function (m, i) {
      var cx = L + slot * i + slot / 2, x = cx - bw / 2, base = T + ph;
      var vis = series.filter(function (s) { return (s.valores[i] || 0) > 0; });
      vis.forEach(function (s, j) {
        var v = s.valores[i], h = Math.max(1, (v / maxv) * ph), top = base - h, topo = j === vis.length - 1;
        var gap = j > 0 ? 2 : 0;
        var hh = Math.max(0.5, h - gap);
        out += topo
          ? '<path class="evo-bar" style="animation-delay:' + (i * 35) + 'ms" d="M' + x + ',' + (base - gap) + 'V' + (top + Math.min(4, hh)) + 'Q' + x + ',' + top + ' ' + (x + Math.min(4, bw / 2)) + ',' + top +
            'H' + (x + bw - Math.min(4, bw / 2)) + 'Q' + (x + bw) + ',' + top + ' ' + (x + bw) + ',' + (top + Math.min(4, hh)) + 'V' + (base - gap) + 'Z" fill="' + s.cor + '"/>'
          : '<rect class="evo-bar" style="animation-delay:' + (i * 35) + 'ms" x="' + x + '" y="' + top + '" width="' + bw + '" height="' + hh + '" fill="' + s.cor + '"/>';
        base = top;
      });
      if (i % passo === 0 || i === n - 1)
        out += '<text x="' + cx + '" y="' + (H - 12) + '" class="evo-ax" text-anchor="middle">' + esc(m.rotulo) + '</text>';
      var tip = '<b>' + esc(m.rotulo) + '</b>' + series.map(function (s) {
        return '<div><i style="background:' + s.cor + '"></i>' + esc(s.label) + '<span>' + brl(s.valores[i]) + '</span></div>';
      }).join('') + (series.length > 1 ? '<div class="t"><i></i>Total<span>' + brl(tot[i]) + '</span></div>' : '') + (o.extraTip ? o.extraTip(i) : '');
      TIPS[id].push(tip);
      out += '<rect class="evo-hit" data-chart="' + id + '" data-i="' + i + '" x="' + (L + slot * i) + '" y="' + T + '" width="' + slot + '" height="' + ph + '"/>';
    });
    if (o.linha) {
      var pts = o.linha.valores.map(function (v, i) { return v == null ? null : [L + slot * i + slot / 2, y(v)]; });
      var d = '', on = false;
      pts.forEach(function (p) { if (!p) { on = false; return; } d += (on ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1); on = true; });
      out += '<path d="' + d + '" fill="none" stroke="' + o.linha.cor + '" stroke-width="2" stroke-dasharray="5 4" class="evo-line" pointer-events="none"/>';
    }
    // valor do último mês, rotulado direto
    if (o.rotularUltimo && n) {
      var lx = L + slot * (n - 1) + slot / 2;
      out += '<text x="' + lx + '" y="' + (y(tot[n - 1]) - 7) + '" class="evo-lbl" text-anchor="middle">' + esc(compacto(tot[n - 1])) + '</text>';
    }
    out += '<line x1="' + L + '" x2="' + (W - Rr) + '" y1="' + (T + ph) + '" y2="' + (T + ph) + '" class="evo-base"/>';
    return '<svg class="evo-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(o.aria || '') + '">' + out + '</svg>';
  }

  /* ---------------- linha (percentual) */
  function linhaPct(meses, valores, o) {
    o = o || {};
    var id = 'evc' + (++seq), W = o.w || 900, H = o.h || 220, L = 50, Rr = 16, T = 18, B = 30;
    var n = meses.length, pw = W - L - Rr, ph = H - T - B;
    var vv = valores.filter(function (v) { return v != null; });
    var maxv = Math.max(1, Math.ceil(Math.max.apply(null, vv.concat([0])) * 1.25));
    var slot = n > 1 ? pw / (n - 1) : pw;
    var x = function (i) { return n > 1 ? L + slot * i : L + pw / 2; };
    var y = function (v) { return T + ph - (v / maxv) * ph; };
    var out = '';
    for (var k = 0; k <= 4; k++) {
      var gv = maxv * k / 4, gy = y(gv);
      out += '<line x1="' + L + '" x2="' + (W - Rr) + '" y1="' + gy + '" y2="' + gy + '" class="evo-grid"/>' +
        '<text x="' + (L - 8) + '" y="' + (gy + 4) + '" class="evo-ax" text-anchor="end">' + pct(gv, 1) + '</text>';
    }
    var d = '', on = false, area = '';
    valores.forEach(function (v, i) {
      if (v == null) { on = false; return; }
      d += (on ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(v).toFixed(1); on = true;
    });
    var first = valores.findIndex(function (v) { return v != null; });
    var last = valores.length - 1 - valores.slice().reverse().findIndex(function (v) { return v != null; });
    if (first >= 0 && last > first && valores.slice(first, last + 1).every(function (v) { return v != null; }))
      area = '<path d="' + d + 'L' + x(last) + ',' + (T + ph) + 'L' + x(first) + ',' + (T + ph) + 'Z" fill="' + o.cor + '" opacity=".08"/>';
    out += area + '<path d="' + d + '" fill="none" stroke="' + o.cor + '" stroke-width="2" class="evo-line"/>';
    var passo = W < 700 ? (n > 12 ? 3 : n > 6 ? 2 : 1) : (n > 18 ? 3 : n > 12 ? 2 : 1);
    TIPS[id] = [];
    var mx = vv.length ? Math.max.apply(null, vv) : null, mn = vv.length ? Math.min.apply(null, vv) : null;
    var marcados = {};
    valores.forEach(function (v, i) {
      if (i % passo === 0 || i === n - 1)
        out += '<text x="' + x(i) + '" y="' + (H - 12) + '" class="evo-ax" text-anchor="middle">' + esc(meses[i].rotulo) + '</text>';
      if (v == null) { TIPS[id].push('<b>' + esc(meses[i].rotulo) + '</b><div>Sem faturamento no mês</div>'); }
      else {
        out += '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="4" fill="' + o.cor + '" stroke="#fff" stroke-width="2"/>';
        if ((v === mx || v === mn || i === last) && !marcados[v]) {
          marcados[v] = 1;
          out += '<text x="' + x(i) + '" y="' + (y(v) - 10) + '" class="evo-lbl" text-anchor="middle">' + pct(v) + '</text>';
        }
        TIPS[id].push('<b>' + esc(meses[i].rotulo) + '</b>' + (o.tip ? o.tip(i) : '<div>' + pct(v) + '</div>'));
      }
      var hw = n > 1 ? slot : pw;
      out += '<rect class="evo-hit" data-chart="' + id + '" data-i="' + i + '" x="' + (x(i) - hw / 2) + '" y="' + T + '" width="' + hw + '" height="' + ph + '"/>';
    });
    return '<svg class="evo-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(o.aria || '') + '">' + out + '</svg>';
  }

  /* ---------------- rosca */
  function rosca(segs, centro, sub) {
    var total = soma(segs.map(function (s) { return s.valor; })) || 1, r = 62, C = 2 * Math.PI * r, ini = 0, arcs = '';
    segs.forEach(function (s, i) {
      if (s.valor <= 0) return;
      var frac = s.valor / total, len = Math.max(0, frac * C - (segs.length > 1 ? 2 : 0));
      arcs += '<circle r="' + r + '" cx="80" cy="80" fill="none" stroke="' + s.cor + '" stroke-width="22" class="evo-arc" style="animation-delay:' + (i * 120) + 'ms"' +
        ' stroke-dasharray="' + len.toFixed(2) + ' ' + (C - len).toFixed(2) + '" transform="rotate(' + (-90 + ini * 360).toFixed(2) + ' 80 80)"><title>' + esc(s.label) + ': ' + brl(s.valor) + ' (' + pct(frac * 100, 1) + ')</title></circle>';
      ini += frac;
    });
    return '<svg viewBox="0 0 160 160" class="evo-donut"><circle r="' + r + '" cx="80" cy="80" fill="none" stroke="#eef0f6" stroke-width="22"/>' + arcs +
      '<text x="80" y="78" text-anchor="middle" class="evo-dc">' + esc(centro) + '</text><text x="80" y="96" text-anchor="middle" class="evo-ds">' + esc(sub) + '</text></svg>';
  }

  /* ---------------- cascata da apuração (um mês) */
  function cascata(m) {
    var a = m.apur;
    var passos = [
      { k: 'Débitos pelas saídas', v: a.deb, t: 'mais' },
      { k: 'Outros débitos e estornos de créditos', v: a.aj_deb_doc + a.outros_deb + a.estornos_cred, t: 'mais' },
      { k: 'Créditos pelas entradas', v: -a.cred, t: 'menos' },
      { k: 'Outros créditos e estornos de débitos', v: -(a.aj_cred_doc + a.outros_cred + a.estornos_deb), t: 'menos' },
      { k: 'Saldo credor do mês anterior', v: -a.sld_ant, t: 'menos' },
      { k: 'Deduções (benefícios e outras)', v: -a.deducoes, t: 'menos' },
    ].filter(function (p) { return Math.abs(p.v) >= 0.005; });
    var res = a.recolher, credor = a.sld_transp;
    var acc = 0, mx = 0, mn = 0;
    passos.forEach(function (p) { acc += p.v; mx = Math.max(mx, acc); mn = Math.min(mn, acc); });
    mx = Math.max(mx, res);
    var W = 900, rowH = 34, T = 6, L = 300, Rr = 130, pw = W - L - Rr, H = T + (passos.length + 1) * rowH + 6;
    var span = (mx - mn) || 1, x = function (v) { return L + (v - mn) / span * pw; };
    var out = '', run = 0;
    passos.forEach(function (p, i) {
      var y0 = T + i * rowH, a0 = run, a1 = run + p.v; run = a1;
      var xa = x(Math.min(a0, a1)), xb = x(Math.max(a0, a1));
      out += '<text x="' + (L - 12) + '" y="' + (y0 + 21) + '" class="evo-wl" text-anchor="end">' + esc(p.k) + '</text>' +
        '<rect class="evo-wbar" style="animation-delay:' + (i * 90) + 'ms" x="' + xa + '" y="' + (y0 + 7) + '" width="' + Math.max(2, xb - xa) + '" height="20" rx="4" fill="' + (p.t === 'mais' ? '#eb6834' : '#2a78d6') + '"/>' +
        '<text x="' + (W - Rr + 10) + '" y="' + (y0 + 21) + '" class="evo-wv">' + (p.v > 0 ? '+ ' : '− ') + esc(brl(Math.abs(p.v))) + '</text>';
      if (i < passos.length - 1) out += '<line x1="' + x(a1) + '" x2="' + x(a1) + '" y1="' + (y0 + 27) + '" y2="' + (y0 + rowH + 7) + '" class="evo-wcon"/>';
    });
    var yr = T + passos.length * rowH;
    out += '<line x1="' + x(0) + '" x2="' + x(0) + '" y1="' + T + '" y2="' + (yr + rowH) + '" class="evo-zero"/>';
    out += '<text x="' + (L - 12) + '" y="' + (yr + 21) + '" class="evo-wl evo-wt" text-anchor="end">' + (credor > 0 ? 'Saldo credor para o mês seguinte' : 'ICMS a recolher') + '</text>' +
      '<rect class="evo-wbar" x="' + x(0) + '" y="' + (yr + 7) + '" width="' + Math.max(2, x(res) - x(0)) + '" height="20" rx="4" fill="#1f2a5a"/>' +
      '<text x="' + (W - Rr + 10) + '" y="' + (yr + 21) + '" class="evo-wv evo-wt">' + esc(brl(credor > 0 ? credor : res)) + '</text>';
    return '<svg class="evo-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Cascata da apuração do ICMS">' + out + '</svg>';
  }

  function leg(itens) {
    return '<div class="evo-leg">' + itens.map(function (s) { return '<span><i style="background:' + s.cor + '"></i>' + esc(s.label) + '</span>'; }).join('') + '</div>';
  }
  function kpi(rot, val, sub, cls) {
    return '<div class="evo-kpi ' + (cls || '') + '"><span>' + esc(rot) + '</span><b>' + val + '</b>' + (sub ? '<small>' + sub + '</small>' : '') + '</div>';
  }
  function card(titulo, sub, corpo, cls) {
    return '<section class="evo-card ' + (cls || '') + '"><h3>' + esc(titulo) + '</h3>' + (sub ? '<p class="evo-sub">' + sub + '</p>' : '') + corpo + '</section>';
  }
  function variacao(p) {
    if (p == null) return '';
    var c = p > 0.5 ? 'up' : p < -0.5 ? 'down' : 'flat';
    return '<em class="evo-var ' + c + '">' + (p > 0 ? '▲ ' : p < 0 ? '▼ ' : '') + pct(Math.abs(p), 1) + '</em>';
  }

  function subAntecipado(t) {
    if (!t.antecipado_total) return 'sem antecipação no período';
    if (t.antecipado_modelo === 'credito') return 'pago em guia própria e creditado na apuração';
    if (t.antecipado_modelo === 'debito_especial')
      return 'recolhido na apuração (débito especial)' + (t.antecipado_creditos > 0 ? ' · crédito aproveitado: ' + brl(t.antecipado_creditos) : '');
    return 'débito especial ' + brl(t.antecipado_deb_esp) + ' · creditado ' + brl(t.antecipado_creditos);
  }

  /* ---------------- textos (frases fixas preenchidas com os números) */
  function resumo(d) {
    var t = d.totais, v = d.variacao, p = d.periodo, f = [];
    f.push('Entre ' + p.ini_rot + ' e ' + p.fim_rot + ' (' + p.meses + (p.meses === 1 ? ' mês' : ' meses') + '), o faturamento líquido somou <b>' + brl(t.liquido) +
      '</b>, com média de <b>' + brl(t.media_fat) + '</b> por mês.');
    if (v && v.pct != null)
      f.push((v.meses_base === 1 ? 'Comparando o primeiro mês com o último' : 'Comparando a média dos ' + v.meses_base + ' primeiros meses com a dos ' + v.meses_base + ' últimos') +
        ', o faturamento ' + (v.pct >= 0.5 ? 'cresceu <b>' + pct(v.pct, 1) + '</b>' : v.pct <= -0.5 ? 'recuou <b>' + pct(-v.pct, 1) + '</b>' : 'ficou estável') +
        (v.trib_pct != null ? ' e os tributos a recolher ' + (v.trib_pct >= 0.5 ? 'subiram <b>' + pct(v.trib_pct, 1) + '</b>' : v.trib_pct <= -0.5 ? 'caíram <b>' + pct(-v.trib_pct, 1) + '</b>' : 'ficaram estáveis') : '') + '.');
    f.push('O total a recolher no período foi de <b>' + brl(t.total_recolher) + '</b>' + (t.carga != null ? ', o que representa uma carga efetiva de ICMS de <b>' + pct(t.carga) + '</b> sobre o faturamento líquido' : '') + '.');
    if (t.antecipado_total > 0)
      f.push('O ICMS antecipado somou <b>' + brl(t.antecipado_total) + '</b> no período' +
        (t.antecipado_modelo === 'credito' ? ', pago em guias próprias e aproveitado como crédito na apuração'
          : t.antecipado_modelo === 'debito_especial' ? ', recolhido junto à apuração como débito especial' +
            (t.antecipado_creditos > 0 ? ' (com <b>' + brl(t.antecipado_creditos) + '</b> aproveitados como crédito)' : '')
          : '') + '.');
    if (t.beneficios > 0) f.push('Os benefícios fiscais lançados na apuração (créditos presumidos, crédito estímulo e similares) reduziram o imposto em <b>' + brl(t.beneficios) + '</b>.');
    if (t.sld_credor_final > 0) f.push('A empresa encerrou o período com saldo credor de ICMS de <b>' + brl(t.sld_credor_final) + '</b> para os meses seguintes.');
    f.push('O mês de maior faturamento foi <b>' + esc(d.destaques.melhor_mes) + '</b> (' + brl(d.destaques.melhor_valor) + ').');
    return f.join(' ');
  }

  /* ---------------- montagem */
  function render(root, d, opts) {
    opts = opts || {};
    seq = 0; TIPS = {};
    var M = d.meses, t = d.totais, p = d.periodo, e = d.empresa;
    var mm = function (fn) { return M.map(fn); };
    var media3 = M.map(function (_, i) { if (i < 2) return null; return (M[i].fat.liquido + M[i - 1].fat.liquido + M[i - 2].fat.liquido) / 3; });
    var serieTrib = [
      { key: 'icms', label: 'ICMS próprio', cor: COR.icms, valores: mm(function (m) { return m.icms_proprio; }) },
      { key: 'deb_esp', label: 'Débitos especiais (antecipação e outros)', cor: COR.deb_esp, valores: mm(function (m) { return m.deb_esp; }) },
      { key: 'st', label: 'ICMS-ST', cor: COR.st, valores: mm(function (m) { return m.st; }) },
      { key: 'difal', label: 'DIFAL', cor: COR.difal, valores: mm(function (m) { return m.difal; }) },
      { key: 'fcp', label: 'FCP', cor: COR.fcp, valores: mm(function (m) { return m.fcp; }) },
      { key: 'ipi', label: 'IPI', cor: COR.ipi, valores: mm(function (m) { return m.ipi; }) },
    ].filter(function (s) { return soma(s.valores) > 0; });
    var h = [];

    // hero
    h.push('<header class="evo-hero"><div class="evo-hero-top"><span class="evo-marca">' + esc(opts.escritorio || 'Liddera | Inteligência em Negócios') +
      '</span><span class="evo-per">' + esc(p.ini_rot) + ' a ' + esc(p.fim_rot) + ' · ' + p.meses + (p.meses === 1 ? ' mês' : ' meses') + '</span></div>' +
      '<h1>Evolução Tributária e de Faturamento</h1><div class="evo-emp">' + esc(e.nome) + ' · CNPJ ' + esc(e.cnpj) + (e.uf ? ' · ' + esc(e.uf) : '') + '</div></header>');
    if (!opts.cliente && (d.avisos || []).length)
      h.push('<div class="evo-avisos"><b>Avisos da análise</b> <span class="evo-so-app">(não vão para o relatório do cliente)</span><ul>' +
        d.avisos.map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('') + '</ul></div>');
    if (opts.cliente && p.faltando && p.faltando.length)
      h.push('<div class="evo-avisos"><b>Observação:</b> os meses ' + esc(p.faltando.join(', ')) + ' não fazem parte desta análise.</div>');
    h.push('<section class="evo-resumo"><div class="evo-rt">Em resumo</div><p>' + resumo(d) + '</p></section>');

    // KPIs
    var v = d.variacao || {};
    h.push('<div class="evo-kpis">' +
      kpi('Faturamento Líquido', brl(t.liquido), 'vendas ' + brl(t.vendas) + ' − devoluções ' + brl(t.devolucoes)) +
      kpi('Faturamento Médio Mensal', brl(t.media_fat), v.pct != null ? 'tendência ' + variacao(v.pct) : '') +
      kpi('Total a Recolher', brl(t.total_recolher), 'média de ' + brl(t.media_recolher) + '/mês' + (v.trib_pct != null ? ' · ' + variacao(v.trib_pct) : ''), 'k-trib') +
      kpi('Carga Efetiva de ICMS', pct(t.carga), 'ICMS, ST, DIFAL e FCP ÷ faturamento líquido', 'k-carga') +
      kpi('ICMS Antecipado', brl(t.antecipado_total), subAntecipado(t), 'k-ant') +
      (t.beneficios > 0 ? kpi('Benefícios Fiscais', brl(t.beneficios), 'redução do imposto no período', 'k-ben')
        : kpi('Saldo Credor Final', brl(t.sld_credor_final), 'disponível para os próximos meses', 'k-ben')) +
      '</div>');

    // faturamento
    h.push(card('Evolução do faturamento', 'Faturamento líquido por mês (vendas menos devoluções de vendas). A linha tracejada é a média móvel de 3 meses.',
      barras(M, [{ label: 'Faturamento líquido', cor: COR.fat, valores: mm(function (m) { return Math.max(0, m.fat.liquido); }) }],
        { linha: { cor: '#1f2a5a', valores: media3 }, rotularUltimo: true, aria: 'Faturamento líquido por mês',
          extraTip: function (i) {
            var f = M[i].fat;
            return '<div class="s">Internas<span>' + brl(f.interna) + '</span></div><div class="s">Interestaduais<span>' + brl(f.interestadual) + '</span></div>' +
              (f.exterior ? '<div class="s">Exportação<span>' + brl(f.exterior) + '</span></div>' : '') +
              '<div class="s">Devoluções<span>− ' + brl(f.devolucoes) + '</span></div>' + (media3[i] != null ? '<div class="s">Média 3 meses<span>' + brl(media3[i]) + '</span></div>' : '');
          } }) + leg([{ label: 'Faturamento líquido', cor: COR.fat }, { label: 'Média móvel de 3 meses (tracejada)', cor: '#1f2a5a' }])));

    // tributos
    h.push(card('Tributos a recolher por mês', 'ICMS próprio (E110), débitos especiais como o ICMS antecipado, ICMS-ST (E210), DIFAL e FCP (E310) e IPI (E520).',
      barras(M, serieTrib, { rotularUltimo: true, aria: 'Tributos a recolher por mês' }) + leg(serieTrib)));

    // carga + mix
    var segMix = [
      { label: 'Vendas internas', valor: t.interna, cor: COR.icms },
      { label: 'Vendas interestaduais', valor: t.interestadual, cor: COR.deb_esp },
      { label: 'Exportação', valor: t.exterior, cor: COR.st },
    ].filter(function (s) { return s.valor > 0; });
    var mixLeg = '<div class="evo-dleg">' + segMix.map(function (s) {
      return '<div><span><i style="background:' + s.cor + '"></i>' + esc(s.label) + '</span><b>' + brl(s.valor) + ' <small>' + pct(s.valor / (t.vendas || 1) * 100, 1) + '</small></b></div>';
    }).join('') + (t.com_st > 0 ? '<div class="evo-dnote">Das vendas, <b>' + brl(t.com_st) + '</b> (' + pct(t.com_st / (t.vendas || 1) * 100, 1) + ') já tiveram o ICMS retido por substituição tributária.</div>' : '') + '</div>';
    h.push('<div class="evo-duo">' +
      card('Carga tributária efetiva', 'ICMS, ST, DIFAL e FCP a recolher ÷ faturamento líquido de cada mês.',
        linhaPct(M, mm(function (m) { return m.carga; }), { cor: COR.carga, w: 560, h: 260, aria: 'Carga efetiva por mês',
          tip: function (i) { var m = M[i]; return '<div>Carga<span>' + pct(m.carga) + '</span></div><div class="s">ICMS total<span>' + brl(m.total_icms) + '</span></div><div class="s">Faturamento<span>' + brl(m.fat.liquido) + '</span></div>'; } })) +
      card('Composição das vendas', 'Vendas do período por destino.', '<div class="evo-dwrap">' + rosca(segMix, compacto(t.vendas), 'em vendas') + mixLeg + '</div>') +
      '</div>');

    // compras x vendas
    h.push(card('Vendas e compras', 'Vendas (saídas de venda) e compras para revenda ou industrialização, mês a mês.',
      barrasAgrupadas(M, [
        { label: 'Vendas', cor: COR.fat, valores: mm(function (m) { return m.fat.vendas; }) },
        { label: 'Compras', cor: COR.compras, valores: mm(function (m) { return m.ent.compras; }) },
      ]) + leg([{ label: 'Vendas', cor: COR.fat }, { label: 'Compras', cor: COR.compras }])));

    // antecipado
    var temAnt = t.antecipado_total > 0 || t.antecipado_creditos > 0;
    if (temAnt) {
      var ajAnt = (d.ajustes || []).filter(function (a) { return a.antecipado; });
      var serAnt = [];
      if (t.antecipado_deb_esp > 0) serAnt.push({ label: 'Antecipado recolhido na apuração (débito especial)', cor: COR.ant_rec, valores: mm(function (m) { return m.antecipado.deb_esp; }) });
      if (t.antecipado_creditos > 0) serAnt.push({ label: t.antecipado_deb_esp > 0 ? 'Crédito de antecipação aproveitado' : 'Antecipado pago em guia e creditado na apuração',
        cor: COR.ant_cred, valores: mm(function (m) { return m.antecipado.creditos; }) });
      h.push(card('ICMS antecipado · ' + brl(t.antecipado_total) + ' no período',
        'Ajustes da apuração (E111) cujo código oficial ou descrição indica antecipação. ' +
        (t.antecipado_modelo === 'credito' ? 'Nesta empresa o antecipado é pago em guia própria, fora da apuração, e aproveitado como crédito: o valor creditado é o antecipado do mês.'
          : t.antecipado_modelo === 'debito_especial' ? 'Nesta empresa o antecipado é recolhido junto à apuração como débito especial; o crédito, quando há, é a recuperação desse mesmo imposto e não é somado de novo.'
          : 'Há meses recolhidos como débito especial e meses pagos em guia própria e creditados; o total usa, mês a mês, o modelo de cada um.'),
        barrasAgrupadas(M, serAnt) + leg(serAnt) + tabelaAjustes(ajAnt, M, true), 'evo-ant'));
    }

    // cascata com seletor de mês
    var opcoesMes = M.map(function (m, i) { return '<option value="' + i + '"' + (i === M.length - 1 ? ' selected' : '') + '>' + esc(m.rotulo) + '</option>'; }).join('');
    h.push(card('Como chegamos ao ICMS a recolher', 'Apuração do ICMS próprio (registro E110) do mês escolhido. Débitos especiais, como o antecipado, são recolhidos à parte e não entram nesta conta.',
      '<div class="evo-sel">Mês: <select class="evo-mes">' + opcoesMes + '</select><span class="evo-sel-extra"></span></div><div class="evo-casc">' + cascata(M[M.length - 1]) + '</div>'));

    // ajustes
    if ((d.ajustes || []).length)
      h.push(card('Ajustes da apuração', 'Todos os lançamentos dos registros E111 (ICMS próprio), E220 (ST) e E311 (DIFAL/FCP), com a descrição oficial da Tabela 5.1.1 da UF.' +
        (d.fonte_tabela ? ' <span class="evo-fonte">Fonte: ' + esc(d.fonte_tabela) + '.</span>' : ''), tabelaAjustes(d.ajustes, M, false)));

    // obrigações
    var obr = [];
    M.forEach(function (m) { (m.obrigacoes || []).forEach(function (o) { obr.push([m, o]); }); });
    if (obr.length)
      h.push(card('Guias a recolher', 'Obrigações declaradas nos registros E116 (ICMS próprio) e E250 (ST), com o código da Tabela 5.4, o vencimento e o código de receita.',
        '<div class="evo-tw"><table class="evo-tab"><thead><tr><th>Mês</th><th>Obrigação</th><th>Cód. receita</th><th>Vencimento</th><th class="n">Valor</th></tr></thead><tbody>' +
        obr.map(function (x) {
          var m = x[0], o = x[1];
          return '<tr><td>' + esc(m.rotulo) + '</td><td>' + esc(o.cod) + ' · ' + esc(o.desc) + (o.uf ? ' (' + esc(o.uf) + ')' : '') + (o.compl ? '<small>' + esc(o.compl) + '</small>' : '') +
            '</td><td>' + esc(o.cod_rec) + '</td><td>' + esc(o.venc_fmt) + '</td><td class="n">' + brl(o.valor) + '</td></tr>';
        }).join('') + '<tr class="tot"><td colspan="4">Total no período</td><td class="n">' + brl(soma(obr.map(function (x) { return x[1].valor; }))) + '</td></tr></tbody></table></div>'));

    // tabela mensal (visão em tabela de todos os gráficos)
    var cols = [['Faturamento líquido', function (m) { return m.fat.liquido; }], ['Vendas internas', function (m) { return m.fat.interna; }],
      ['Interestaduais', function (m) { return m.fat.interestadual; }], ['Devoluções', function (m) { return m.fat.devolucoes; }],
      ['Compras', function (m) { return m.ent.compras; }], ['ICMS próprio', function (m) { return m.icms_proprio; }],
      ['Déb. especiais', function (m) { return m.deb_esp; }], ['ICMS-ST', function (m) { return m.st; }], ['DIFAL', function (m) { return m.difal; }],
      ['FCP', function (m) { return m.fcp; }], ['IPI', function (m) { return m.ipi; }], ['Total a recolher', function (m) { return m.total_recolher; }]]
      .filter(function (c) { return soma(M.map(c[1])) !== 0 || /Faturamento|Total|ICMS próprio/.test(c[0]); });
    h.push(card('Quadro mês a mês', 'Todos os valores dos gráficos acima, em tabela.',
      '<div class="evo-tw"><table class="evo-tab evo-mensal"><thead><tr><th>Mês</th>' + cols.map(function (c) { return '<th class="n">' + esc(c[0]) + '</th>'; }).join('') + '<th class="n">Carga</th></tr></thead><tbody>' +
      M.map(function (m) { return '<tr><td>' + esc(m.rotulo) + '</td>' + cols.map(function (c) { return '<td class="n">' + NF.format(c[1](m) || 0) + '</td>'; }).join('') + '<td class="n">' + pct(m.carga) + '</td></tr>'; }).join('') +
      '<tr class="tot"><td>Total</td>' + cols.map(function (c) { return '<td class="n">' + NF.format(soma(M.map(c[1]))) + '</td>'; }).join('') + '<td class="n">' + pct(t.carga) + '</td></tr></tbody></table></div>'));

    if ((opts.recado || '').trim())
      h.push('<section class="evo-recado"><div class="evo-rt">Recado do escritório</div><p>' + esc(opts.recado.trim()).replace(/\n/g, '<br>') + '</p></section>');
    if (opts.tecnico !== false) h.push(card('De onde vem cada número', 'Todos os valores foram lidos dos SPED Fiscais (EFD ICMS/IPI) entregues pela empresa, sem estimativas.', glossario(d), 'evo-glos'));
    h.push('<footer class="evo-rod">Relatório gerencial elaborado a partir das EFD ICMS/IPI de ' + esc(p.ini_rot) + ' a ' + esc(p.fim_rot) +
      '. Documento destinado ao acompanhamento tributário da empresa. Em caso de dúvidas, fale com sua equipe contábil. · ' + esc(opts.escritorio || 'Liddera | Inteligência em Negócios') + '</footer>');

    root.innerHTML = '<div class="evo">' + h.join('') + '<div class="evo-tip" hidden></div></div>';
    ligar(root, d);
  }

  function barrasAgrupadas(meses, series) {
    var id = 'evc' + (++seq), W = 900, H = 250, L = 64, Rr = 12, T = 14, B = 34;
    var n = meses.length, pw = W - L - Rr, ph = H - T - B, k = series.length;
    var maxv = niceMax(Math.max.apply(null, [0].concat.apply([], series.map(function (s) { return s.valores; }))) * 1.04);
    var y = function (v) { return T + ph - (v / maxv) * ph; };
    var slot = pw / n, gw = Math.min(64, slot * 0.7), bw = (gw - 2 * (k - 1)) / k;
    var out = '';
    for (var g2 = 0; g2 <= 4; g2++) {
      var gv = maxv * g2 / 4, gy = y(gv);
      out += '<line x1="' + L + '" x2="' + (W - Rr) + '" y1="' + gy + '" y2="' + gy + '" class="evo-grid"/><text x="' + (L - 8) + '" y="' + (gy + 4) + '" class="evo-ax" text-anchor="end">' + esc(compacto(gv)) + '</text>';
    }
    var passo = n > 18 ? 3 : n > 12 ? 2 : 1;
    TIPS[id] = [];
    meses.forEach(function (m, i) {
      var cx = L + slot * i + slot / 2, x0 = cx - gw / 2;
      series.forEach(function (s, j) {
        var v = s.valores[i] || 0, hh = Math.max(v > 0 ? 1 : 0, v / maxv * ph), x = x0 + j * (bw + 2), top = T + ph - hh, rr = Math.min(4, bw / 2, hh);
        if (hh > 0) out += '<path class="evo-bar" style="animation-delay:' + (i * 35) + 'ms" d="M' + x + ',' + (T + ph) + 'V' + (top + rr) + 'Q' + x + ',' + top + ' ' + (x + rr) + ',' + top + 'H' + (x + bw - rr) + 'Q' + (x + bw) + ',' + top + ' ' + (x + bw) + ',' + (top + rr) + 'V' + (T + ph) + 'Z" fill="' + s.cor + '"/>';
      });
      if (i % passo === 0 || i === n - 1) out += '<text x="' + cx + '" y="' + (H - 12) + '" class="evo-ax" text-anchor="middle">' + esc(m.rotulo) + '</text>';
      TIPS[id].push('<b>' + esc(m.rotulo) + '</b>' + series.map(function (s) { return '<div><i style="background:' + s.cor + '"></i>' + esc(s.label) + '<span>' + brl(s.valores[i]) + '</span></div>'; }).join(''));
      out += '<rect class="evo-hit" data-chart="' + id + '" data-i="' + i + '" x="' + (L + slot * i) + '" y="' + T + '" width="' + slot + '" height="' + ph + '"/>';
    });
    out += '<line x1="' + L + '" x2="' + (W - Rr) + '" y1="' + (T + ph) + '" y2="' + (T + ph) + '" class="evo-base"/>';
    return '<svg class="evo-svg" viewBox="0 0 ' + W + ' ' + H + '">' + out + '</svg>';
  }

  function tabelaAjustes(lista, M, compacta) {
    if (!lista.length) return '';
    var cab = '<th>Código</th><th>Descrição</th><th>Natureza</th>' + (compacta ? '' : M.map(function (m) { return '<th class="n">' + esc(m.rotulo) + '</th>'; }).join('')) + '<th class="n">Total</th>';
    var linhas = lista.map(function (a) {
      var tags = (a.antecipado ? '<span class="evo-tag ant">Antecipado</span>' : '') + (a.beneficio ? '<span class="evo-tag ben">Benefício</span>' : '');
      var desc = esc(a.desc_oficial || a.compl || 'Sem descrição') + (a.desc_oficial && a.compl ? '<small>' + esc(a.compl) + '</small>' : '');
      return '<tr><td class="cod">' + esc(a.cod) + '<small>' + esc(a.reg) + ' · ' + esc(a.apuracao) + '</small></td><td class="desc">' + tags + desc + '</td><td>' + esc(a.nat_rotulo) + '</td>' +
        (compacta ? '' : M.map(function (m) { var v = a.por_mes[m.comp]; return '<td class="n">' + (v ? NF.format(v) : '<span class="z">—</span>') + '</td>'; }).join('')) +
        '<td class="n"><b>' + brl(a.total) + '</b></td></tr>';
    }).join('');
    return '<div class="evo-tw"><table class="evo-tab evo-aj"><thead><tr>' + cab + '</tr></thead><tbody>' + linhas + '</tbody></table></div>';
  }

  function glossario(d) {
    var itens = [
      ['Faturamento líquido', 'Soma do campo VL_OPR dos registros analíticos (C190, C590, D190 e demais) com CFOP de venda (5.1xx, 5.4xx, 6.1xx, 7.1xx…), menos as devoluções de venda recebidas (1.2xx, 2.2xx, 1.410/1.411…). Notas canceladas ou denegadas não entram.'],
      ['Compras', 'Entradas com CFOP de compra para revenda ou industrialização (1.1xx, 2.1xx, 1.403, 2.403…).'],
      ['ICMS próprio', 'Campo VL_ICMS_RECOLHER do registro E110 (apuração do ICMS das operações próprias).'],
      ['Débitos especiais', 'Campo DEB_ESP do E110: valores recolhidos fora da apuração normal, como o ICMS antecipado. O detalhe está nos ajustes E111 de natureza 5.'],
      ['ICMS-ST', 'Campos VL_ICMS_RECOL_ST + DEB_ESP_ST do registro E210, somados para todas as UFs do E200.'],
      ['DIFAL e FCP', 'Campos VL_RECOL_DIFAL + DEB_ESP_DIFAL e VL_RECOL_FCP + DEB_ESP_FCP do registro E310.'],
      ['IPI', 'Campo VL_SD_IPI (saldo devedor) do registro E520.'],
      ['ICMS antecipado', 'Ajustes E111 cuja descrição oficial (Tabela 5.1.1 da UF) ou descrição complementar indica antecipação. Total do mês: o débito especial de antecipação (natureza 5), quando a empresa recolhe junto à apuração; ou o crédito de antecipação (naturezas 2 e 4), quando paga em guia própria e credita depois. O mesmo imposto nunca é somado duas vezes.'],
      ['Benefícios fiscais', 'Ajustes que reduzem o imposto (naturezas 2, 3 e 4) identificados como crédito presumido, crédito estímulo ou incentivo, ou marcados no campo IND_BENEFICIO.'],
      ['Carga efetiva', '(ICMS próprio + débitos especiais + ST + DIFAL + FCP) ÷ faturamento líquido do mês. O IPI não entra nesta conta.'],
    ];
    return '<div class="evo-gl">' + itens.map(function (x) { return '<div><b>' + esc(x[0]) + '</b><span>' + esc(x[1]) + '</span></div>'; }).join('') + '</div>' +
      '<p class="evo-sub" style="margin-top:10px">Arquivos analisados: ' + esc((d.arquivos || []).join(', ')) + '.</p>';
  }

  function ligar(root, d) {
    var box = root.querySelector('.evo'), tip = root.querySelector('.evo-tip');
    box.addEventListener('mousemove', function (ev) {
      var h = ev.target.closest && ev.target.closest('.evo-hit');
      if (!h) { tip.hidden = true; return; }
      var arr = TIPS[h.getAttribute('data-chart')];
      if (!arr) return;
      tip.innerHTML = arr[+h.getAttribute('data-i')];
      tip.hidden = false;
      var r = box.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
      var x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 14;
      if (x + tw > r.width - 4) x = ev.clientX - r.left - tw - 14;
      if (ev.clientY + th + 20 > window.innerHeight) y = ev.clientY - r.top - th - 10;
      tip.style.left = x + 'px'; tip.style.top = y + 'px';
    });
    box.addEventListener('mouseleave', function () { tip.hidden = true; });
    var sel = root.querySelector('.evo-mes');
    if (sel) {
      var upd = function () {
        var m = d.meses[+sel.value];
        root.querySelector('.evo-casc').innerHTML = cascata(m);
        var ex = root.querySelector('.evo-sel-extra');
        ex.innerHTML = (m.deb_esp > 0 ? 'Débitos especiais recolhidos à parte: <b>' + brl(m.deb_esp) + '</b>' : '') +
          (m.apur.sld_ant > 0 ? (m.deb_esp > 0 ? ' · ' : '') + 'Saldo credor recebido do mês anterior: <b>' + brl(m.apur.sld_ant) + '</b>' : '');
      };
      sel.addEventListener('change', upd);
      upd();
    }
  }

  g.EvoDash = { render: render, COR: COR };
})(typeof window !== 'undefined' ? window : this);

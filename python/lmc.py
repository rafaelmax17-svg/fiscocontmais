# -*- coding: utf-8 -*-
"""Substituir LMC de Combustíveis no SPED Fiscal (Admin › Substituir LMC).

Posto de combustível: o cliente manda o SPED com o LMC (Livro de Movimentação de Combustíveis — registros 1300 a 1399
do Bloco 1: 1300/1310/1320 movimentação diária, por tanque e por bico; 1350/1360/1370 bombas, lacres e bicos; 1390/1391
controle de usina) certo, mas o SPED gerado pelo Domínio sai com esse bloco errado ou incompleto.

O que faz (gera arquivo NOVO; os originais nunca são alterados):
  1) confere se os dois arquivos são da mesma empresa (CNPJ) e do mesmo período;
  2) tira do SPED do Domínio todos os registros 1300 a 1399 e coloca, no mesmo lugar do Bloco 1, os do SPED do cliente,
     na ordem em que vieram;
  3) produto do LMC que não existe no cadastro (0200) do SPED do Domínio é copiado do SPED do cliente (com a unidade
     0190, se faltar) — senão o PVA recusa o 1300 ("COD_ITEM não existe no 0200");
  4) ajusta o 1010 (IND_COMB = S quando há LMC; IND_USINA conforme o 1390);
  5) recalcula os fechamentos de bloco e o Bloco 9.
Guia Prático da EFD ICMS/IPI: registros 1010, 1300, 1310, 1320, 1350, 1360, 1370, 1390 e 1391.
"""
import os
import sys
import json
import html as _html

import fiscal_core as fc


def _reg(l):
    c = l.split('|')
    return c[1] if len(c) > 2 else ''


def _eh_lmc(r):
    return len(r) == 4 and r.isdigit() and 1300 <= int(r) <= 1399


def _n(s):
    s = (s or '').strip()
    if not s:
        return 0.0
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except ValueError:
        return 0.0


def _dividir(texto):
    quebra = '\r\n' if '\r\n' in texto else '\n'
    final = texto.endswith(quebra)
    linhas = texto.split(quebra)
    if final:
        linhas = linhas[:-1]
    return linhas, quebra, final


def _cab(linhas):
    for l in linhas[:3]:
        c = l.split('|')
        if len(c) > 9 and c[1] == '0000':
            return {'dt_ini': c[4], 'dt_fin': c[5], 'nome': c[6], 'cnpj': c[7] or c[8], 'uf': c[9]}
    return {}


def _resumo_lmc(linhas, nomes):
    """Totais por produto (1300) e quantidade de registros do LMC."""
    cont, prods = {}, {}
    for l in linhas:
        r = _reg(l)
        if not _eh_lmc(r):
            continue
        cont[r] = cont.get(r, 0) + 1
        if r == '1300':
            c = l.split('|')
            if len(c) < 12:
                continue
            cod = c[2]
            p = prods.setdefault(cod, {'cod': cod, 'descr': nomes.get(cod, ''), 'dias': 0, 'abertura': None, 'entradas': 0.0,
                                       'saidas': 0.0, 'perdas': 0.0, 'ganhos': 0.0, 'fechamento': 0.0, 'serie': []})
            p['dias'] += 1
            if p['abertura'] is None:
                p['abertura'] = _n(c[4])
            p['entradas'] += _n(c[5])
            p['saidas'] += _n(c[7])
            p['perdas'] += _n(c[9])
            p['ganhos'] += _n(c[10])
            p['fechamento'] = _n(c[11])
            p['serie'].append({'dia': c[3], 'saidas': _n(c[7]), 'entradas': _n(c[5])})
    for p in prods.values():
        p['abertura'] = p['abertura'] or 0.0
        for k in ('entradas', 'saidas', 'perdas', 'ganhos'):
            p[k] = round(p[k], 3)
    return cont, list(prods.values())


def substituir(texto_sem, texto_com):
    """Devolve (texto_novo, resumo). Em erro, texto_novo é None e resumo['erro'] explica."""
    sem, quebra, final = _dividir(texto_sem)
    com, _, _ = _dividir(texto_com)
    cab_s, cab_c = _cab(sem), _cab(com)
    if not cab_s or not cab_c:
        return None, {'erro': 'Um dos arquivos não é um SPED Fiscal (falta o registro 0000).'}
    if cab_s.get('cnpj') != cab_c.get('cnpj'):
        return None, {'erro': f'Os arquivos são de empresas diferentes: CNPJ {cab_s.get("cnpj")} (Domínio) e {cab_c.get("cnpj")} (cliente).'}
    if (cab_s.get('dt_ini'), cab_s.get('dt_fin')) != (cab_c.get('dt_ini'), cab_c.get('dt_fin')):
        return None, {'erro': 'Os arquivos são de períodos diferentes: '
                              f'{cab_s.get("dt_ini")}–{cab_s.get("dt_fin")} (Domínio) e {cab_c.get("dt_ini")}–{cab_c.get("dt_fin")} (cliente).'}
    lmc_cli = [l for l in com if _eh_lmc(_reg(l))]
    if not any(_reg(l) == '1300' for l in lmc_cli):
        return None, {'erro': 'O SPED do cliente não tem LMC (registro 1300). Confira se escolheu os arquivos na ordem certa: '
                              '1º o do Domínio, 2º o do cliente.'}
    nomes_s = {c[2]: c[3] for c in (l.split('|') for l in sem if l.startswith('|0200|')) if len(c) > 3}
    nomes_c = {c[2]: c[3] for c in (l.split('|') for l in com if l.startswith('|0200|')) if len(c) > 3}
    cont_antes, prods_antes = _resumo_lmc(sem, nomes_s)
    cont_depois, prods_depois = _resumo_lmc(lmc_cli, {**nomes_s, **nomes_c})

    # monta o arquivo: tira 1300–1399 do Domínio e põe os do cliente no mesmo lugar do Bloco 1
    saida, pos, removidos = [], None, 0
    for l in sem:
        r = _reg(l)
        if _eh_lmc(r):
            removidos += 1
            if pos is None:
                pos = len(saida)
            continue
        if pos is None and r[:1] == '1' and r.isdigit() and int(r) > 1399:
            pos = len(saida)                  # sem LMC no Domínio: entra antes do primeiro registro depois do 1399
        saida.append(l)
    if pos is None:
        return None, {'erro': 'O SPED do Domínio não tem o Bloco 1 (registro 1990).'}
    saida[pos:pos] = lmc_cli

    # cadastro: produto (0200) e unidade (0190) que o LMC usa e o Domínio não tem
    avisos, novos_0200, novos_0190 = [], [], []
    tem_0200 = set(nomes_s)
    tem_0190 = {c[2] for c in (l.split('|') for l in sem if l.startswith('|0190|')) if len(c) > 2}
    lin_0200_cli = {c.split('|')[2]: c for c in com if c.startswith('|0200|')}
    lin_0190_cli = {c.split('|')[2]: c for c in com if c.startswith('|0190|')}
    usados = sorted({l.split('|')[2] for l in lmc_cli if _reg(l) == '1300'})
    for cod in usados:
        if cod in tem_0200:
            continue
        lin = lin_0200_cli.get(cod)
        if not lin:
            avisos.append(f'O produto {cod} do LMC não está no 0200 de nenhum dos dois arquivos: cadastre antes de transmitir.')
            continue
        novos_0200.append(lin)
        und = lin.split('|')[6] if len(lin.split('|')) > 6 else ''
        if und and und not in tem_0190 and und in lin_0190_cli and lin_0190_cli[und] not in novos_0190:
            novos_0190.append(lin_0190_cli[und])
    if novos_0200 or novos_0190:
        i190 = max((i for i, l in enumerate(saida) if _reg(l) in ('0150', '0175', '0190')), default=None)
        if novos_0190 and i190 is not None:
            saida[i190 + 1:i190 + 1] = novos_0190
        i200 = max((i for i, l in enumerate(saida) if _reg(l) in ('0190', '0200', '0205', '0206', '0210', '0220', '0221')), default=None)
        if novos_0200 and i200 is not None:
            saida[i200 + 1:i200 + 1] = novos_0200

    # 1010: indicadores do Bloco 1
    tem_usina = any(_reg(l) == '1390' for l in lmc_cli)
    for i, l in enumerate(saida):
        if _reg(l) == '1010':
            c = l.split('|')
            if len(c) > 5:
                c[4] = 'S'
                c[5] = 'S' if tem_usina else c[5]
                saida[i] = '|'.join(c)
            break

    saida = fc._recalcula_bloco9_global(saida)
    saida = fc._recalcula_fechamentos_bloco(saida)
    novo = quebra.join(saida) + (quebra if final else '')
    if cont_antes.get('1300', 0) > cont_depois.get('1300', 0):
        avisos.append(f'O SPED do Domínio tinha mais registros 1300 ({cont_antes.get("1300", 0)}) que o do cliente ({cont_depois.get("1300", 0)}). '
                      'Confira se os arquivos foram escolhidos na ordem certa: 1º o do Domínio, 2º o do cliente.')
    if novos_0200:
        avisos.append(f'{len(novos_0200)} produto(s) do LMC não estavam no 0200 do Domínio e foram copiados do SPED do cliente: '
                      + ', '.join(f'{l.split("|")[2]} – {l.split("|")[3]}' for l in novos_0200[:6]) + '.')
    if novos_0190:
        avisos.append(f'{len(novos_0190)} unidade(s) de medida (0190) copiada(s) do SPED do cliente.')
    return novo, {
        'empresa': {'nome': cab_s.get('nome', ''), 'cnpj': cab_s.get('cnpj', ''), 'dt_ini': cab_s.get('dt_ini', ''), 'dt_fin': cab_s.get('dt_fin', '')},
        'registros_removidos': removidos, 'registros_incluidos': len(lmc_cli),
        'por_registro_antes': cont_antes, 'por_registro_depois': cont_depois,
        'produtos_antes': prods_antes, 'produtos_depois': prods_depois,
        'produtos_0200_incluidos': len(novos_0200), 'unidades_0190_incluidas': len(novos_0190),
        'avisos': avisos,
    }


# ------------------------------------------------------------------ dashboard
def _f(v, casas=2):
    return f'{v:,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def gerar_html(res, logo=''):
    e = res.get('empresa', {})
    esc = _html.escape
    dt = lambda s: f'{s[:2]}/{s[2:4]}/{s[4:]}' if len(s or '') == 8 else (s or '')
    antes = {p['cod']: p for p in res.get('produtos_antes', [])}
    cards = ''
    for k, p in enumerate(res.get('produtos_depois', [])):
        a = antes.get(p['cod'])
        mx = max([s['saidas'] for s in p['serie']] + [1])
        barras = ''.join(f'<i title="{dt(s["dia"])}: {_f(s["saidas"], 3)}" style="--h:{s["saidas"] / mx * 100:.1f}%;--d:{j * 25}ms"></i>'
                         for j, s in enumerate(p['serie']))
        dif = ''
        if a:
            ds = p['saidas'] - a['saidas']
            dif = (f'<div class="cmp">Domínio tinha <b>{a["dias"]}</b> dia(s) e saídas de <b>{_f(a["saidas"], 3)}</b>'
                   + (f' · diferença <b class="{"neg" if ds < 0 else "pos"}">{"+" if ds >= 0 else ""}{_f(ds, 3)}</b>' if abs(ds) > 0.0005 else ' · <b class="pos">igual</b>') + '</div>')
        else:
            dif = '<div class="cmp">Não havia LMC deste produto no SPED do Domínio.</div>'
        cards += f'''<div class="card" style="--i:{k}"><div class="ct"><b>{esc(p["descr"] or p["cod"])}</b><small>cód. {esc(p["cod"])} · {p["dias"]} dia(s)</small></div>
          <div class="kp"><div><span>Abertura</span><b>{_f(p["abertura"], 3)}</b></div><div><span>Entradas</span><b>{_f(p["entradas"], 3)}</b></div>
          <div><span>Saídas</span><b>{_f(p["saidas"], 3)}</b></div><div><span>Perdas</span><b class="neg">{_f(p["perdas"], 3)}</b></div>
          <div><span>Ganhos</span><b class="pos">{_f(p["ganhos"], 3)}</b></div><div><span>Fechamento</span><b>{_f(p["fechamento"], 3)}</b></div></div>
          <div class="bars" title="Saídas por dia">{barras}</div>{dif}</div>'''
    regs = sorted(set(res.get('por_registro_antes', {})) | set(res.get('por_registro_depois', {})))
    tab = ''.join(f'<tr><td>{r}</td><td class="n">{res["por_registro_antes"].get(r, 0)}</td><td class="n"><b>{res["por_registro_depois"].get(r, 0)}</b></td></tr>' for r in regs)
    av = ''.join(f'<li>{esc(a)}</li>' for a in res.get('avisos', []))
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Substituição do LMC</title><style>
body{{margin:0;padding:24px;background:#f4f5fa;font-family:Inter,Segoe UI,system-ui,sans-serif;color:#141b2d}}
.hd{{display:flex;justify-content:space-between;align-items:center;background:linear-gradient(120deg,#1f2a5a,#2f4090);color:#fff;border-radius:16px;padding:18px 22px}}
.hd h1{{margin:4px 0 2px;font-size:20px}}.hd small{{color:#dfe5ff;font-size:12.5px}}.hd .k{{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#cdd6ff}}
.hd img{{height:38px;background:#fff;border-radius:8px;padding:4px 8px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}}.kpis div{{background:#fff;border-radius:14px;padding:12px 14px;box-shadow:0 4px 14px rgba(20,27,45,.06)}}
.kpis span{{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#5a6785}}.kpis b{{font-size:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}}
.card{{background:#fff;border-radius:16px;padding:16px 18px;box-shadow:0 4px 14px rgba(20,27,45,.06);opacity:0;transform:translateY(8px);animation:in .5s ease forwards;animation-delay:calc(var(--i)*120ms)}}
.ct b{{font-size:15px}}.ct small{{display:block;color:#5a6785;font-size:12px}}
.kp{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}}.kp span{{display:block;font-size:10.5px;text-transform:uppercase;color:#5a6785}}.kp b{{font-size:15px;font-variant-numeric:tabular-nums}}
.bars{{display:flex;align-items:flex-end;gap:2px;height:90px;border-bottom:1px solid #e8ebf3}}
.bars i{{flex:1;background:linear-gradient(#4f46e5,#2f4090);border-radius:3px 3px 0 0;height:0;animation:up .7s ease forwards;animation-delay:var(--d)}}
.cmp{{font-size:12.5px;color:#3a4566;margin-top:10px}}.neg{{color:#b3261e}}.pos{{color:#0b7a55}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:6px 10px;border-bottom:1px solid #eef0f6;text-align:left}}.n{{text-align:right}}
.box{{background:#fff;border-radius:16px;padding:16px 18px;margin-top:14px;box-shadow:0 4px 14px rgba(20,27,45,.06)}}
.av{{background:#fff6e5;border:1px solid #f2d39b;border-radius:12px;padding:10px 14px;font-size:13px;margin-top:14px}}
@keyframes in{{to{{opacity:1;transform:none}}}}@keyframes up{{to{{height:var(--h)}}}}
</style></head><body>
<div class="hd"><div><div class="k">Substituição do LMC de combustíveis · registros 1300 a 1399</div><h1>{esc(e.get("nome", ""))}</h1>
<small>CNPJ {esc(e.get("cnpj", ""))} · período {dt(e.get("dt_ini"))} a {dt(e.get("dt_fin"))}</small></div>{f'<img src="{logo}">' if logo else ''}</div>
<div class="kpis"><div><span>Registros removidos (Domínio)</span><b>{res.get("registros_removidos", 0)}</b></div>
<div><span>Registros incluídos (cliente)</span><b>{res.get("registros_incluidos", 0)}</b></div>
<div><span>Produtos no LMC</span><b>{len(res.get("produtos_depois", []))}</b></div>
<div><span>Produtos copiados para o 0200</span><b>{res.get("produtos_0200_incluidos", 0)}</b></div></div>
{f'<div class="av"><b>Atenção</b><ul>{av}</ul></div>' if av else ''}
<div class="grid">{cards}</div>
<div class="box"><b>Registros do LMC</b><table><thead><tr><th>Registro</th><th class="n">Domínio (antes)</th><th class="n">Cliente (agora)</th></tr></thead><tbody>{tab}</tbody></table></div>
</body></html>'''


# ------------------------------------------------------------------ CLI
def main_cli(argv):
    """substituir-lmc SPED_DOMINIO.txt --com-lmc SPED_CLIENTE.txt --saida NOVO.txt [--json resumo.json] [--html painel.html]"""
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    if len(argv) < 2 or not opt('--com-lmc') or not opt('--saida'):
        print(main_cli.__doc__)
        return 1
    try:
        texto_sem, enc = fc._ler_sped(argv[1])
        texto_com, _ = fc._ler_sped(opt('--com-lmc'))
        novo, res = substituir(texto_sem, texto_com)
    except Exception as e:  # pragma: no cover
        novo, res = None, {'erro': f'Falha ao ler os arquivos: {e}'}
    # ordem: JSON e HTML antes do SPED — a tela espera pelo SPED e depois lê o resumo
    if opt('--json'):
        fc._out(opt('--json'), json.dumps(res, ensure_ascii=False))
    if opt('--html'):
        fc._out(opt('--html'), gerar_html(res, fc._logo_uri()) if not res.get('erro') else
                f'<html><body style="font-family:sans-serif;padding:24px"><h3>Não foi possível substituir o LMC</h3><p>{_html.escape(res["erro"])}</p></body></html>')
    if novo is not None:
        fc._grava_sped(opt('--saida'), novo, enc)
    elif not opt('--html'):
        # a tela espera o arquivo de saída ter conteúdo; grava uma linha em branco para ela seguir e mostrar o erro do resumo
        with open(opt('--saida'), 'w') as fh:
            fh.write('\n')
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main_cli(sys.argv[1:]))

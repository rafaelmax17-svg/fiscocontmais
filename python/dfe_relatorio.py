# -*- coding: utf-8 -*-
"""Relatório das Baixas DF-e (NF-e, CT-e e NFC-e) de uma empresa num mês, e PDF das notas.

Lê os XMLs que as Baixas DF-e já salvaram em  <pasta>/<MM-AAAA>/<empresa>/<NF-e Entradas|CT-e Entradas|NF-e Saídas|NFC-e Saídas>/XML
e grava, na mesma pasta da empresa:
  · PDF de cada NF-e (DANFE, danfe.py) e de cada CT-e (DACTE, dacte.py) em  <tipo>/PDF/<chave>.pdf  — NFC-e não tem PDF;
    nota cancelada sai com a tarja CANCELADA; PDF que já existe não é refeito;
  · "Relatório DF-e - MM-AAAA.html": página única, sem internet, com painel animado (totais, movimento por dia, valor
    por tipo de documento, principais fornecedores e clientes, CFOP, UF de origem) e a lista das notas com link para o
    XML e o PDF. Nada sai do computador: o relatório fica só na pasta.

    python fiscal_core.py dfe-relatorio --pasta BASE --empresa NOME --cnpj CNPJ --competencia AAAA-MM [--pdf 1] --json r.json
"""
import json
import os
import re
from datetime import datetime

import manifestacao as mf
import nfe_chave as nc

GRUPOS = [  # ordem fixa = cor fixa no relatório
    ('nfe-e', 'NF-e Entradas', 'nfe'),
    ('cte-e', 'CT-e Entradas', 'cte'),
    ('nfe-s', 'NF-e Saídas', 'nfe'),
    ('nfce-s', 'NFC-e Saídas', 'nfce'),
]


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _doc_de(bloco):
    return mf._txt(bloco, 'CNPJ') or mf._txt(bloco, 'CPF')


def _ler_nfe(txt):
    ch = re.search(r'Id="NFe(\d{44})"', txt)
    if not ch:
        return None
    emit = (mf._blocos(txt, 'emit') or [''])[0]
    dest = (mf._blocos(txt, 'dest') or [''])[0]
    tot = (mf._blocos(txt, 'ICMSTot') or [''])[0]
    cfops = {}
    for det in mf._blocos(txt, 'det'):
        cf = mf._txt(det, 'CFOP')
        if cf:
            cfops[cf] = round(cfops.get(cf, 0) + _num(mf._txt(det, 'vProd')), 2)
    return {'ch': ch.group(1), 'n': mf._txt(txt, 'nNF'), 'serie': mf._txt(txt, 'serie'), 'mod': mf._txt(txt, 'mod'),
            'dh': mf._txt(txt, 'dhEmi') or mf._txt(txt, 'dEmi'), 'nat': mf._txt(txt, 'natOp'),
            'emit': mf._txt(emit, 'xNome'), 'emitDoc': _doc_de(emit), 'emitUf': mf._txt(emit, 'UF'),
            'dest': mf._txt(dest, 'xNome'), 'destDoc': _doc_de(dest), 'destUf': mf._txt(dest, 'UF'),
            'valor': _num(mf._txt(tot, 'vNF')), 'icms': _num(mf._txt(tot, 'vICMS')), 'st': _num(mf._txt(tot, 'vST')),
            'ipi': _num(mf._txt(tot, 'vIPI')), 'cfops': cfops, 'prot': bool(re.search(r'<(?:\w+:)?protNFe\b', txt))}


def _ler_cte(txt):
    ch = re.search(r'Id="CTe(\d{44})"', txt)
    if not ch:
        return None
    emit = (mf._blocos(txt, 'emit') or [''])[0]
    rem = (mf._blocos(txt, 'rem') or [''])[0]
    icms = (mf._blocos(txt, 'ICMS') or [''])[0]
    cf = mf._txt(txt, 'CFOP')
    v = _num(mf._txt(txt, 'vTPrest'))
    return {'ch': ch.group(1), 'n': mf._txt(txt, 'nCT'), 'serie': mf._txt(txt, 'serie'), 'mod': '57', 'dh': mf._txt(txt, 'dhEmi'),
            'nat': mf._txt(txt, 'natOp'), 'emit': mf._txt(emit, 'xNome'), 'emitDoc': _doc_de(emit), 'emitUf': mf._txt(txt, 'UFIni'),
            'dest': mf._txt(rem, 'xNome'), 'destDoc': _doc_de(rem), 'destUf': mf._txt(txt, 'UFFim'),
            'valor': v, 'icms': _num(mf._txt(icms, 'vICMS') or mf._txt(icms, 'vICMSOutraUF')), 'st': 0.0, 'ipi': 0.0,
            'cfops': {cf: v} if cf else {}, 'prot': bool(re.search(r'<(?:\w+:)?protCTe\b', txt))}


def _canceladas(pasta_xml):
    out = set()
    for nome in os.listdir(pasta_xml):
        if '-evento-110111' in nome or 'canc' in nome.lower():
            m = re.match(r'(\d{44})', nome)
            if m:
                out.add(m.group(1))
                continue
            try:
                with open(os.path.join(pasta_xml, nome), encoding='utf-8', errors='replace') as fh:
                    t = fh.read()
                if mf._txt(t, 'tpEvento') == '110111':
                    out.add(mf._txt(t, 'chNFe') or mf._txt(t, 'chCTe'))
            except OSError:
                pass
    return out


def _pdf(tipo, xml_txt, destino, cancelada):
    if tipo == 'cte':
        import dacte
        dacte.gerar_pdf(xml_txt, destino, tarja='CANCELADO' if cancelada else '')
    else:
        import danfe
        danfe.gerar_pdf(xml_txt, destino, tarja='CANCELADA' if cancelada else '')


def coletar(pasta_emp, pdf=True, progresso=None):
    grupos, pdfs, pdf_erros, total_xml = [], 0, [], 0
    for gid, nome, tipo in GRUPOS:
        pasta_xml = os.path.join(pasta_emp, nome, 'XML')
        docs = []
        if os.path.isdir(pasta_xml):
            canc = _canceladas(pasta_xml)
            arquivos = sorted(f for f in os.listdir(pasta_xml) if f.lower().endswith('.xml') and '-evento-' not in f)
            for k, f in enumerate(arquivos):
                caminho = os.path.join(pasta_xml, f)
                try:
                    with open(caminho, encoding='utf-8', errors='replace') as fh:
                        txt = fh.read()
                except OSError:
                    continue
                d = _ler_cte(txt) if tipo == 'cte' else _ler_nfe(txt)
                if not d:
                    continue
                total_xml += 1
                d['canc'] = d['ch'] in canc
                d['xml'] = f'{nome}/XML/{f}'
                d['pdf'] = ''
                if tipo in ('nfe', 'cte'):
                    rel = f'{nome}/PDF/{d["ch"]}.pdf'
                    alvo = os.path.join(pasta_emp, nome, 'PDF', f'{d["ch"]}.pdf')
                    if os.path.exists(alvo):
                        d['pdf'] = rel
                    elif pdf:
                        try:
                            os.makedirs(os.path.dirname(alvo), exist_ok=True)
                            _pdf(tipo, txt, alvo, d['canc'])
                            d['pdf'] = rel
                            pdfs += 1
                        except Exception as e:      # um XML com problema não para o resto
                            pdf_erros.append(f'{f}: {str(e)[:120]}')
                            try:
                                os.remove(alvo)
                            except OSError:
                                pass
                if progresso and k % 25 == 0:
                    try:
                        with open(progresso, 'w', encoding='utf-8') as fh:
                            json.dump({'tipo': nome, 'feitos': k, 'total': len(arquivos)}, fh)
                    except OSError:
                        pass
                docs.append(d)
        grupos.append({'id': gid, 'nome': nome, 'tipo': tipo, 'docs': docs})
    return grupos, pdfs, pdf_erros, total_xml


def _compacto(grupos):
    """Só o que o painel usa (NFC-e pode ter milhares de cupons)."""
    out = []
    for g in grupos:
        lista = []
        for d in g['docs']:
            dia = (d['dh'] or '')[:10]
            item = [d['ch'], d['n'], d['serie'], dia, d['emit'], d['emitDoc'], d['emitUf'], d['dest'], d['destDoc'], d['destUf'],
                    round(d['valor'], 2), round(d['icms'], 2), round(d['st'], 2), round(d['ipi'], 2), 1 if d['canc'] else 0,
                    d['xml'], d['pdf'], d['cfops'] if g['tipo'] != 'nfce' else {}]
            lista.append(item)
        out.append({'id': g['id'], 'nome': g['nome'], 'tipo': g['tipo'], 'docs': lista})
    return out


def gerar(base, empresa, cnpj, competencia, pdf=True, progresso=None, publico=None):
    if not re.match(r'^\d{4}-\d{2}$', competencia or ''):
        return {'erro': 'Competência inválida.'}
    a, m = competencia.split('-')
    pasta_emp = os.path.join(base, f'{m}-{a}', nc._limpa_nome(empresa))
    if not os.path.isdir(pasta_emp):
        return {'erro': f'Ainda não há notas baixadas de {m}/{a} para esta empresa.'}
    grupos, pdfs, pdf_erros, total = coletar(pasta_emp, pdf, progresso)
    if not total:
        return {'erro': f'Nenhum XML de NF-e, CT-e ou NFC-e em {m}/{a} para esta empresa.'}
    dados = {'empresa': empresa, 'cnpj': re.sub(r'\D', '', cnpj or ''), 'comp': f'{m}/{a}', 'compIso': competencia,
             'gerado': datetime.now().strftime('%d/%m/%Y %H:%M'), 'grupos': _compacto(grupos)}
    js = json.dumps(dados, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = HTML.replace('/*__DADOS__*/null', js).replace('__TITULO__', _esc(f'Relatório DF-e · {empresa} · {m}/{a}'))
    destino = os.path.join(pasta_emp, f'Relatório DF-e - {m}-{a}.html')
    with open(destino, 'w', encoding='utf-8') as fh:
        fh.write(html)
    if publico:                       # cópia para a pasta do cliente: sem os links (os arquivos estão nos zips)
        dados_pub = dict(dados, grupos=[dict(g, docs=[d[:15] + ['', ''] + d[17:] for d in g['docs']]) for g in dados['grupos']])
        js_pub = json.dumps(dados_pub, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
        os.makedirs(os.path.dirname(publico), exist_ok=True)
        with open(publico + '.tmp', 'w', encoding='utf-8') as fh:
            fh.write(HTML.replace('/*__DADOS__*/null', js_pub).replace('__TITULO__', _esc(f'Relatório DF-e · {empresa} · {m}/{a}')))
        os.replace(publico + '.tmp', publico)
    resumo = {g['id']: {'qtd': len(g['docs']), 'valor': round(sum(d['valor'] for d in g['docs'] if not d['canc']), 2),
                        'canceladas': sum(1 for d in g['docs'] if d['canc'])} for g in grupos}
    return {'ok': True, 'html': destino, 'pdfs': pdfs, 'pdf_erros': len(pdf_erros), 'pdf_erros_det': pdf_erros[:10],
            'resumo': resumo, 'pasta': pasta_emp, 'publico': publico or ''}


def _esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def main_cli(argv):
    def opt(n, d=None):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else d
    try:
        r = gerar(opt('--pasta'), opt('--empresa', ''), opt('--cnpj', ''), opt('--competencia', ''),
                  pdf=opt('--pdf', '1') != '0', progresso=opt('--progresso'), publico=opt('--publico'))
    except Exception as e:
        r = {'erro': str(e)[:400]}
    saida = opt('--json')
    if saida:
        with open(saida, 'w', encoding='utf-8') as fh:
            json.dump(r, fh, ensure_ascii=False)
    else:
        print(json.dumps(r, ensure_ascii=False))
    return 0


from dfe_relatorio_html import HTML  # noqa: E402  (modelo da página, embutido para o executável)

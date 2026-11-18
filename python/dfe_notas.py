# -*- coding: utf-8 -*-
"""Baixas DF-e · NF-e e CT-e de ENTRADA pelo Ambiente Nacional + extração do arquivo de SAÍDAS do DFe-Download (SEFIN-RO).

ENTRADAS (todas as empresas, com o certificado cadastrado nas Baixas DF-e)
  • NF-e: NFeDistribuicaoDFe 1.01 (Ambiente Nacional), consulta pela sequência da empresa (distNSU / ultNSU), 50 documentos
    por chamada. Vem o XML completo (procNFe) da nota que já teve manifestação (de qualquer sistema) ou em que a empresa é
    autorizada; nos outros casos vem só o resumo (resNFe). Com a opção ligada, o sistema registra a "Ciência da Operação"
    (evento 210210) só nas notas que vieram como resumo — nota que já tem ciência ou outra manifestação vem completa e
    é só baixada. Depois da ciência, tenta pegar o XML pela chave (consChNFe); o que não vier agora chega na próxima busca.
  • CT-e: CTeDistribuicaoDFe 1.00 (Ambiente Nacional), mesma sequência por NSU; o CT-e vem completo (procCTe).
  • Regra do Ambiente Nacional (NT 2014.002): quando a sequência chega ao fim (cStat 137 ou ultNSU = maxNSU) só se pode
    consultar de novo depois de 1 hora; antes disso a SEFAZ responde 656 (consumo indevido) e bloqueia por 1 hora.
    A posição (ultNSU) e o horário liberado ficam guardados por empresa, então nada é baixado duas vezes.
  • Pastas (mesma organização das NFS-e): <pasta>/<MM-AAAA da emissão>/<empresa>/NF-e Entradas/XML/<chave>-procNFe.xml
    e .../CT-e Entradas/XML/<chave>-procCTe.xml. Nota da própria empresa como emitente não entra (não é entrada).

SAÍDAS (só empresas de RO): o arquivo do DFe-Download da SEFIN é baixado pela janela do sistema (a pessoa digita o
código da imagem). extrair_saidas() abre o ZIP (e ZIPs dentro dele), separa cada XML no mês da emissão em
NF-e Saídas / NFC-e Saídas e devolve quantidade, total e canceladas.

CLI: python fiscal_core.py dfe-notas --entrada pedido.json --json resultado.json [--progresso p.json]
     (pedido com o certificado e a senha; o arquivo é apagado assim que é lido)
     python fiscal_core.py dfe-extrair --zip arquivo.zip --pasta BASE --empresa NOME --cnpj CNPJ --tipo nfe|nfce --json r.json
"""
import base64
import gzip
import io
import json
import os
import re
import time
import zipfile
from datetime import datetime, timedelta

import manifestacao as mf
import nfe_chave as nc

URL_NFE = 'https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx'
URL_CTE = 'https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx'
UF_COD = {v: k for k, v in mf.UF_SIGLA.items()}
MAX_CHAMADAS = 40          # 40 × 50 documentos por empresa e tipo em cada busca
MAX_CIENCIA = 60           # ciências por busca (o resto na próxima)
MAX_CONSCH = 20            # consultas por chave depois da ciência (o resto vem pela sequência na próxima busca)


def _agora():
    return datetime.now().astimezone()


def _iso(d):
    return d.replace(microsecond=0).isoformat()


def _mes_pasta(dh):
    m = re.match(r'(\d{4})-(\d{2})', dh or '')
    return f'{m.group(2)}-{m.group(1)}' if m else 'sem-data'


def _pasta(base, dh, empresa, sub):
    return os.path.join(base, _mes_pasta(dh), nc._limpa_nome(empresa), sub, 'XML')


def _soap(sess, url, ns_wsdl, metodo, dados, acao):
    env = ('<?xml version="1.0" encoding="utf-8"?><soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
           f'<soap12:Body><{metodo} xmlns="{ns_wsdl}">{dados}</{metodo}></soap12:Body></soap12:Envelope>')
    r = sess.post(url, data=env.encode('utf-8'), timeout=60,
                  headers={'Content-Type': f'application/soap+xml; charset=utf-8; action="{ns_wsdl}/{acao}"'})
    r.raise_for_status()
    return r.text


def _dist(sess, tipo, cnpj, cuf, ult):
    if tipo == 'nfe':
        ns = 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe'
        dados = (f'<nfeDadosMsg><distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01"><tpAmb>1</tpAmb>'
                 f'<cUFAutor>{cuf}</cUFAutor><CNPJ>{cnpj}</CNPJ><distNSU><ultNSU>{ult}</ultNSU></distNSU></distDFeInt></nfeDadosMsg>')
        xml = _soap(sess, URL_NFE, ns, 'nfeDistDFeInteresse', dados, 'nfeDistDFeInteresse')
    else:
        ns = 'http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe'
        dados = (f'<cteDadosMsg><distDFeInt xmlns="http://www.portalfiscal.inf.br/cte" versao="1.00"><tpAmb>1</tpAmb>'
                 f'<cUFAutor>{cuf}</cUFAutor><CNPJ>{cnpj}</CNPJ><distNSU><ultNSU>{ult}</ultNSU></distNSU></distDFeInt></cteDadosMsg>')
        xml = _soap(sess, URL_CTE, ns, 'cteDistDFeInteresse', dados, 'cteDistDFeInteresse')
    ret = re.search(r'<(?:\w+:)?retDistDFeInt\b.*?</(?:\w+:)?retDistDFeInt>', xml, re.S)
    ret = ret.group(0) if ret else xml
    docs = []
    for m in re.finditer(r'<(?:\w+:)?docZip\b([^>]*)>([^<]+)</(?:\w+:)?docZip>', ret):
        try:
            doc = gzip.decompress(base64.b64decode(m.group(2))).decode('utf-8', 'replace')
        except Exception:
            continue
        nsu = re.search(r'NSU="(\d+)"', m.group(1))
        docs.append((nsu.group(1) if nsu else '', re.sub(r'^\s*<\?xml[^>]*\?>', '', doc).strip()))
    return {'cstat': mf._txt(ret, 'cStat'), 'motivo': mf._txt(ret, 'xMotivo'), 'ult': mf._txt(ret, 'ultNSU'),
            'max': mf._txt(ret, 'maxNSU'), 'docs': docs}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _cnpj_de(bloco):
    return mf._txt(bloco, 'CNPJ') or mf._txt(bloco, 'CPF')


def _salvar_nfe(proc, base, empresa, cnpj):
    ch = re.search(r'Id="NFe(\d{44})"', proc)
    ch = ch.group(1) if ch else mf._txt(proc, 'chNFe')
    emit = (mf._blocos(proc, 'emit') or [''])[0]
    dest = (mf._blocos(proc, 'dest') or [''])[0]
    if _cnpj_de(emit) == cnpj:
        return None, 'propria'
    if _cnpj_de(dest) != cnpj:
        return None, 'outra'          # empresa só transportadora/autorizada: não é entrada dela
    dh = mf._txt(proc, 'dhEmi') or mf._txt(proc, 'dEmi')
    cam = nc._grava(os.path.join(_pasta(base, dh, empresa, 'NF-e Entradas'), f'{ch}-procNFe.xml'),
                    '<?xml version="1.0" encoding="UTF-8"?>' + proc)
    return {'chave': ch, 'emitente': mf._txt(emit, 'xNome'), 'valor': _num(mf._txt(proc, 'vNF')), 'dh': dh, 'xml': cam}, 'ok'


def _salvar_cte(proc, base, empresa, cnpj):
    ch = re.search(r'Id="CTe(\d{44})"', proc)
    ch = ch.group(1) if ch else mf._txt(proc, 'chCTe')
    emit = (mf._blocos(proc, 'emit') or [''])[0]
    if _cnpj_de(emit) == cnpj:
        return None, 'propria'
    dh = mf._txt(proc, 'dhEmi')
    cam = nc._grava(os.path.join(_pasta(base, dh, empresa, 'CT-e Entradas'), f'{ch}-procCTe.xml'),
                    '<?xml version="1.0" encoding="UTF-8"?>' + proc)
    return {'chave': ch, 'emitente': mf._txt(emit, 'xNome'), 'valor': _num(mf._txt(proc, 'vTPrest')), 'dh': dh, 'xml': cam}, 'ok'


def _prog(arq, d):
    if arq:
        try:
            with open(arq, 'w', encoding='utf-8') as fh:
                json.dump(d, fh)
        except OSError:
            pass


def baixar_entradas(sess, pfx, senha, cnpj, empresa, uf, base, estado, tipos, com_ciencia, competencia, progresso=None):
    """estado: {'nfe': {'ult': '...', 'proxima': iso}, 'cte': {...}} (atualizado e devolvido)."""
    cuf = UF_COD.get((uf or '').upper(), '11')
    comp = competencia or ''          # AAAA-MM
    res = {'nfe': None, 'cte': None}
    estado = dict(estado or {})
    for tipo in tipos:
        st = dict(estado.get(tipo) or {})
        r = {'baixadas': [], 'resumos': [], 'canceladas': [], 'ciencias': 0, 'ciencia_erros': [], 'propria': 0, 'outra': 0,
             'chamadas': 0, 'aviso': '', 'erro': ''}
        prox = st.get('proxima')
        if prox:
            try:
                quando = datetime.fromisoformat(prox)
                if quando > _agora():
                    r['aviso'] = (f'O Ambiente Nacional só libera nova consulta às {quando:%H:%M} de {quando:%d/%m} '
                                  '(regra da SEFAZ: 1 hora depois de chegar ao fim da sequência).')
                    res[tipo] = r
                    continue
            except ValueError:
                pass
        ult = st.get('ult') or '0' * 15
        resumos = {}
        while r['chamadas'] < MAX_CHAMADAS:
            try:
                d = _dist(sess, tipo, cnpj, cuf, ult)
            except Exception as e:
                r['erro'] = f'Falha ao consultar o Ambiente Nacional: {mf._erro_legivel(e)}'
                break
            r['chamadas'] += 1
            cst = d['cstat']
            if cst == '656':
                st['proxima'] = _iso(_agora() + timedelta(hours=1))
                r['aviso'] = 'A SEFAZ pediu para aguardar 1 hora (consumo indevido). O sistema tenta de novo depois desse horário.'
                break
            if cst not in ('137', '138'):
                r['erro'] = f"SEFAZ: {cst} · {d['motivo']}".strip(' ·')
                break
            for _nsu, doc in d['docs']:
                if tipo == 'nfe':
                    if re.search(r'<(?:\w+:)?nfeProc\b', doc):
                        it, como = _salvar_nfe(doc, base, empresa, cnpj)
                        if it:
                            r['baixadas'].append(it)
                            resumos.pop(it['chave'], None)
                        else:
                            r[como] += 1
                    elif re.search(r'<(?:\w+:)?resNFe\b', doc):
                        ch = mf._txt(doc, 'chNFe')
                        info = {'chave': ch, 'emitente': mf._txt(doc, 'xNome'), 'valor': _num(mf._txt(doc, 'vNF')),
                                'dh': mf._txt(doc, 'dhEmi'), 'csit': mf._txt(doc, 'cSitNFe')}
                        if info['csit'] == '3':
                            r['canceladas'].append(info)
                        elif not any(b['chave'] == ch for b in r['baixadas']):
                            resumos[ch] = info
                    elif re.search(r'<(?:\w+:)?(resEvento|procEventoNFe)\b', doc) and mf._txt(doc, 'tpEvento') == '110111':
                        ch = mf._txt(doc, 'chNFe')
                        resumos.pop(ch, None)
                        try:
                            nc._grava(os.path.join(_pasta(base, mf._txt(doc, 'dhEvento') or mf._txt(doc, 'dhRecbto'), empresa, 'NF-e Entradas'),
                                                   f'{ch}-evento-110111.xml'), '<?xml version="1.0" encoding="UTF-8"?>' + doc)
                        except OSError:
                            pass
                        r['canceladas'].append({'chave': ch, 'emitente': '', 'valor': 0.0, 'dh': mf._txt(doc, 'dhEvento'), 'csit': '3'})
                else:
                    if re.search(r'<(?:\w+:)?cteProc\b', doc):
                        it, como = _salvar_cte(doc, base, empresa, cnpj)
                        if it:
                            r['baixadas'].append(it)
                        else:
                            r[como] += 1
                    elif re.search(r'<(?:\w+:)?procEventoCTe\b', doc) and mf._txt(doc, 'tpEvento') == '110111':
                        r['canceladas'].append({'chave': mf._txt(doc, 'chCTe'), 'emitente': '', 'valor': 0.0, 'dh': mf._txt(doc, 'dhEvento'), 'csit': '3'})
            if d['ult']:
                ult = d['ult']
            _prog(progresso, {'tipo': tipo, 'chamadas': r['chamadas'], 'baixadas': len(r['baixadas'])})
            if cst == '137' or (d['ult'] and d['max'] and d['ult'] >= d['max']):
                st['proxima'] = _iso(_agora() + timedelta(hours=1))
                break
            time.sleep(0.6)
        st['ult'] = ult
        # ciência só no que veio como resumo (nota já manifestada vem completa e foi só baixada)
        if tipo == 'nfe' and com_ciencia and resumos:
            chave_priv = cert_b64 = None
            feitas = []
            for ch, info in list(resumos.items())[:MAX_CIENCIA]:
                if info['csit'] != '1':
                    continue
                try:
                    if chave_priv is None:
                        chave_priv, cert_b64 = nc._carrega_pfx(pfx, senha)
                    ok, cs, mot = nc.ciencia(sess, ch, cnpj, chave_priv, cert_b64)
                except Exception as e:
                    ok, cs, mot = False, '', mf._erro_legivel(e)
                if ok:
                    r['ciencias'] += 1
                    feitas.append(ch)
                else:
                    r['ciencia_erros'].append({'chave': ch, 'motivo': f'{cs} {mot}'.strip()})
                time.sleep(0.4)
            if feitas:
                time.sleep(4)
            for ch in feitas[:MAX_CONSCH]:
                try:
                    dd = nc.distribuicao(sess, ch, cnpj, cuf)
                except Exception:
                    break
                if dd['cstat'] == '656':
                    break
                if dd['proc']:
                    it, como = _salvar_nfe(dd['proc'], base, empresa, cnpj)
                    if it:
                        r['baixadas'].append(it)
                        resumos.pop(ch, None)
                time.sleep(1.0)
        r['resumos'] = list(resumos.values())
        if tipo == 'nfe' and r['resumos'] and not com_ciencia:
            r['aviso'] = (r['aviso'] + ' ' if r['aviso'] else '') + \
                f"{len(r['resumos'])} nota(s) vieram só como resumo: o XML completo sai depois da Ciência da Operação."
        elif tipo == 'nfe' and r['resumos'] and r['ciencias']:
            r['aviso'] = (r['aviso'] + ' ' if r['aviso'] else '') + \
                f"Ciência registrada em {r['ciencias']} nota(s): o XML completo das que ainda faltam chega na próxima busca (depois de 1 hora)."
        no_mes = [b for b in r['baixadas'] if (b['dh'] or '')[:7] == comp] if comp else r['baixadas']
        r['mes'] = {'qtd': len(no_mes), 'valor': round(sum(b['valor'] for b in no_mes), 2)}
        por_mes = {}
        for b in r['baixadas']:          # a sequência da SEFAZ traz todos os meses: cada nota fica na pasta do mês de emissão
            k = (b['dh'] or '')[:7] or 'sem-data'
            por_mes[k] = por_mes.get(k, 0) + 1
        r['meses'] = por_mes
        estado[tipo] = st
        res[tipo] = r
    return res, estado


def processar(p):
    from fiscal_core import _extrair_cert_chave_temp
    try:
        cert_pem, key_pem, tmp = _extrair_cert_chave_temp(p['pfx'], p['senha'])
    except Exception as e:
        return {'erro': f'Não consegui abrir o certificado: {e}'}
    sess = mf.sessao(cert_pem, key_pem)
    try:
        res, estado = baixar_entradas(sess, p['pfx'], p['senha'], re.sub(r'\D', '', p['cnpj']), p['empresa'], p.get('uf', ''),
                                      p['pasta'], p.get('estado') or {}, p.get('tipos') or ['nfe', 'cte'],
                                      bool(p.get('ciencia')), p.get('competencia', ''), p.get('progresso'))
        return {'ok': True, 'res': res, 'estado': estado}
    finally:
        sess.close()
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


# ------------------------------------------------------------------ saídas (arquivo do DFe-Download da SEFIN-RO)
def _xmls_do_zip(dados, profundidade=0):
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile:
        return
    for info in z.infolist():
        if info.is_dir():
            continue
        nome = info.filename.lower()
        conteudo = z.read(info)
        if nome.endswith('.zip') and profundidade < 3:
            yield from _xmls_do_zip(conteudo, profundidade + 1)
        elif nome.endswith('.xml'):
            yield info.filename, conteudo


def _itens_das_partes(caminhos):
    """Lê os arquivos baixados de um pedido. Cada ARQUIVO/PARTE normalmente é um ZIP completo; se vier um ZIP
    dividido em pedaços (nenhum abre sozinho), junta os pedaços na ordem e abre como um só."""
    blocos = []
    for c in caminhos:
        with open(c, 'rb') as fh:
            blocos.append((os.path.basename(c), fh.read()))
    itens, soltos = [], []
    for nome, dados in blocos:
        lido = None
        if zipfile.is_zipfile(io.BytesIO(dados)):
            try:
                lido = list(_xmls_do_zip(dados))
            except Exception:           # pedaço de um ZIP dividido: o fim do ZIP está aqui, o começo em outra parte
                lido = None
        if lido is not None:
            itens.extend(lido)
        elif dados.lstrip()[:1] == b'<':
            itens.append((nome, dados))
        else:
            soltos.append(dados)
    if soltos:
        junto = b''.join(soltos)
        if junto[:4] == b'PK\x07\x08':            # assinatura de ZIP dividido
            junto = junto[4:]
        try:
            itens.extend(_xmls_do_zip(junto))
        except Exception:
            if not itens:
                return None
        if not itens:
            return None
    return itens


def extrair_saidas(zip_path, base, empresa, cnpj, tipo, competencia=''):
    # O arquivo de NF-e do DFe-Download traz as notas EMITIDAS e as RECEBIDAS pela empresa (2.4.5): emitente = empresa vai
    # para NF-e Saídas; destinatário = empresa vai para NF-e Entradas, com o mesmo nome de arquivo das entradas do Ambiente
    # Nacional (<chave>-procNFe.xml), sem duplicar. É a segunda opção quando o Ambiente Nacional manda aguardar 1 hora.
    sub = 'NFC-e Saídas' if tipo == 'nfce' else 'NF-e Saídas'
    ent = {}
    cnpj = re.sub(r'\D', '', cnpj or '')
    caminhos = zip_path if isinstance(zip_path, (list, tuple)) else [zip_path]
    itens = _itens_das_partes(caminhos)
    if itens is None:
        return {'erro': 'O arquivo baixado da SEFIN não é um ZIP nem um XML.'}
    notas, canc, outros, outras_emp = {}, set(), 0, 0
    eventos = []
    for nome, conteudo in itens:
        txt = conteudo.decode('utf-8', 'replace')
        txt = re.sub(r'^﻿', '', txt)
        corpo = re.sub(r'^\s*<\?xml[^>]*\?>', '', txt).strip()
        if re.search(r'<(?:\w+:)?(nfeProc|NFe)\b', corpo):
            ch = re.search(r'Id="NFe(\d{44})"', corpo)
            ch = ch.group(1) if ch else ''
            emit = (mf._blocos(corpo, 'emit') or [''])[0]
            dest = (mf._blocos(corpo, 'dest') or [''])[0]
            dh = mf._txt(corpo, 'dhEmi') or mf._txt(corpo, 'dEmi')
            if cnpj and _cnpj_de(emit) != cnpj:
                if tipo == 'nfe' and ch and _cnpj_de(dest) == cnpj:          # nota recebida pela empresa: entrada
                    cam = nc._grava(os.path.join(_pasta(base, dh, empresa, 'NF-e Entradas'), f'{ch}-procNFe.xml'),
                                    '<?xml version="1.0" encoding="UTF-8"?>' + corpo)
                    ent[ch] = {'chave': ch, 'dh': dh, 'valor': _num(mf._txt(corpo, 'vNF')), 'xml': cam}
                else:
                    outras_emp += 1
                continue
            cam = nc._grava(os.path.join(_pasta(base, dh, empresa, sub), f'{ch or os.path.splitext(os.path.basename(nome))[0]}-nfe.xml'),
                            '<?xml version="1.0" encoding="UTF-8"?>' + corpo)
            notas[ch or cam] = {'chave': ch, 'dh': dh, 'valor': _num(mf._txt(corpo, 'vNF')), 'mod': mf._txt(corpo, 'mod'), 'xml': cam}
        elif re.search(r'<(?:\w+:)?(procEventoNFe|evento)\b', corpo):
            ch = mf._txt(corpo, 'chNFe')
            if mf._txt(corpo, 'tpEvento') == '110111':
                canc.add(ch)
            eventos.append((ch, corpo))
        else:
            outros += 1
    for ch, corpo in eventos:       # evento guardado junto da nota
        n = notas.get(ch) or ent.get(ch)
        if n:
            tp = mf._txt(corpo, 'tpEvento') or 'evento'
            nc._grava(os.path.join(os.path.dirname(n['xml']), f'{ch}-evento-{tp}.xml'), '<?xml version="1.0" encoding="UTF-8"?>' + corpo)
    lista = list(notas.values())
    ativos = [n for n in lista if n['chave'] not in canc]
    no_mes = [n for n in ativos if not competencia or (n['dh'] or '')[:7] == competencia]
    return {'ok': True, 'tipo': tipo, 'qtd': len(lista), 'canceladas': sum(1 for n in lista if n['chave'] in canc),
            'valor': round(sum(n['valor'] for n in ativos), 2), 'mes': {'qtd': len(no_mes), 'valor': round(sum(n['valor'] for n in no_mes), 2)},
            'outras_empresas': outras_emp, 'ignorados': outros,
            'pasta': os.path.dirname(lista[0]['xml']) if lista else '',
            'entradas': _resumo_ent(list(ent.values()), canc, competencia)}


def _resumo_ent(lista, canc, competencia):
    ativos = [n for n in lista if n['chave'] not in canc]
    no_mes = [n for n in ativos if not competencia or (n['dh'] or '')[:7] == competencia]
    return {'qtd': len(lista), 'canceladas': sum(1 for n in lista if n['chave'] in canc), 'valor': round(sum(n['valor'] for n in ativos), 2),
            'mes': {'qtd': len(no_mes), 'valor': round(sum(n['valor'] for n in no_mes), 2)},
            'pasta': os.path.dirname(lista[0]['xml']) if lista else ''}


def main_cli(argv):
    def opt(n, d=None):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else d
    saida = opt('--json')
    try:
        if argv and argv[0] == 'extrair':
            zips = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == '--zip']
            r = extrair_saidas(zips, opt('--pasta'), opt('--empresa', ''), opt('--cnpj', ''), opt('--tipo', 'nfe'), opt('--competencia', ''))
        else:
            ent = opt('--entrada')
            with open(ent, encoding='utf-8') as fh:
                p = json.load(fh)
            try:
                os.remove(ent)              # tem a senha do certificado
            except OSError:
                pass
            p['progresso'] = opt('--progresso')
            r = processar(p)
    except Exception as e:
        r = {'erro': str(e)[:400]}
    if saida:
        with open(saida, 'w', encoding='utf-8') as fh:
            json.dump(r, fh, ensure_ascii=False)
    return 0 if not r.get('erro') else 1

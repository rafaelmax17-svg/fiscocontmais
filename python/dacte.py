# -*- coding: utf-8 -*-
"""DACTE (Documento Auxiliar do CT-e) em PDF, gerado a partir do XML do CT-e (modelo 57) — retrato, A4.

Quadros na ordem do Manual de Orientação do Contribuinte do CT-e (leiaute do DACTE): emitente, quadro "DACTE" com o
modal, código de barras da chave de acesso e protocolo de autorização; modelo, série, número, emissão, tipo do CT-e e
do serviço; CFOP e natureza da operação; início e término da prestação; remetente, destinatário, expedidor, recebedor
e tomador; informações da carga e quantidades; componentes do valor da prestação; imposto; documentos originários;
observações; e dados específicos do modal rodoviário (RNTRC).
"""
import re
import sys

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.graphics.barcode import code128

from danfe import _limpa, _t, _n, _m, _doc, _data, _chave_fmt, _D, _tarja, W, H, M, LW

TP_CTE = {'0': 'NORMAL', '1': 'COMPLEMENTO DE VALORES', '2': 'ANULAÇÃO', '3': 'SUBSTITUTO'}
TP_SERV = {'0': 'NORMAL', '1': 'SUBCONTRATAÇÃO', '2': 'REDESPACHO', '3': 'REDESPACHO INTERMEDIÁRIO', '4': 'SERV. VINCULADO A MULTIMODAL',
           '6': 'TRANSPORTE DE PESSOAS', '7': 'TRANSPORTE DE VALORES', '8': 'EXCESSO DE BAGAGEM'}
TOMA = {'0': 'REMETENTE', '1': 'EXPEDIDOR', '2': 'RECEBEDOR', '3': 'DESTINATÁRIO', '4': 'OUTROS'}
MODAL = {'01': 'RODOVIÁRIO', '02': 'AÉREO', '03': 'AQUAVIÁRIO', '04': 'FERROVIÁRIO', '05': 'DUTOVIÁRIO', '06': 'MULTIMODAL'}
UNID = {'00': 'M3', '01': 'KG', '02': 'TON', '03': 'UNIDADE', '04': 'LITROS', '05': 'MMBTU'}


def ler(texto):
    raiz = _limpa(texto)
    inf = raiz if raiz.tag == 'infCte' else raiz.find('.//infCte')
    if inf is None:
        raise ValueError('O arquivo não é um CT-e.')
    return {'raiz': raiz, 'inf': inf, 'chave': (inf.get('Id') or '').replace('CTe', ''), 'prot': raiz.find('.//protCTe/infProt')}


def _ender(no):
    if no is None:
        return None
    for tag in ('enderEmit', 'enderReme', 'enderDest', 'enderExped', 'enderReceb', 'enderToma'):
        e = no.find(tag)
        if e is not None:
            return e
    return None


def _participante(D, x, y, w, h, titulo, no):
    c = D.c
    D.caixa(x, y, w, h, titulo)
    if no is None:
        return
    e = _ender(no)
    doc = _t(no, 'CNPJ') or _t(no, 'CPF')
    c.setFont('Helvetica-Bold', 7)
    c.drawString(x + 3, H - y - 15, D.cabe(_t(no, 'xNome'), 'Helvetica-Bold', 7, w - 6))
    c.setFont('Helvetica', 6.3)
    end = f'{_t(e, "xLgr")}, {_t(e, "nro")} {_t(e, "xCpl")}'.strip(' ,')
    c.drawString(x + 3, H - y - 24, D.cabe(end, 'Helvetica', 6.3, w - 6))
    c.drawString(x + 3, H - y - 32, D.cabe(f'{_t(e, "xBairro")} · {_t(e, "xMun")} - {_t(e, "UF")} · CEP {_t(e, "CEP")}', 'Helvetica', 6.3, w - 6))
    c.drawString(x + 3, H - y - 40, D.cabe(f'CNPJ/CPF: {_doc(doc)}    IE: {_t(no, "IE")}    Fone: {_t(no, "fone") or _t(e, "fone")}', 'Helvetica', 6.3, w - 6))


def gerar_pdf(texto_xml, saida, tarja=''):
    d = ler(texto_xml)
    inf, chave, prot = d['inf'], d['chave'], d['prot']
    ide, emit = inf.find('ide'), inf.find('emit')
    rem, dest, exped, receb = inf.find('rem'), inf.find('dest'), inf.find('exped'), inf.find('receb')
    vprest = inf.find('vPrest')
    norm = inf.find('infCTeNorm')
    carga = norm.find('infCarga') if norm is not None else None
    ee = emit.find('enderEmit') if emit is not None else None

    c = canvas.Canvas(saida, pagesize=A4)
    c.setTitle(f'DACTE {chave}')
    c.setAuthor('FiscoCont+')
    D = _D(c)
    dt, hr = _data(_t(ide, 'dhEmi'))
    num = _t(ide, 'nCT')
    modal = MODAL.get(_t(ide, 'modal'), _t(ide, 'modal'))

    y = M
    # emitente
    D.caixa(M, y, 230, 92)
    D.linhas(M + 6, y + 14, 218, _t(emit, 'xNome'), tam=9, max_l=2)
    c.setFont('Helvetica-Bold', 9)
    end = f'{_t(ee, "xLgr")}, {_t(ee, "nro")} {_t(ee, "xCpl")}'.strip()
    D.linhas(M + 6, y + 40, 218, f'{end}\n{_t(ee, "xBairro")} - CEP {_t(ee, "CEP")}\n{_t(ee, "xMun")} - {_t(ee, "UF")}   Fone: {_t(ee, "fone")}\n'
             f'CNPJ: {_doc(_t(emit, "CNPJ") or _t(emit, "CPF"))}   IE: {_t(emit, "IE")}', tam=6.6)
    # quadro DACTE
    x2 = M + 230
    D.caixa(x2, y, 105, 92)
    c.setFont('Helvetica-Bold', 13)
    c.drawCentredString(x2 + 52.5, H - y - 17, 'DACTE')
    c.setFont('Helvetica', 5.6)
    c.drawCentredString(x2 + 52.5, H - y - 25, 'Documento Auxiliar do Conhecimento')
    c.drawCentredString(x2 + 52.5, H - y - 31, 'de Transporte Eletrônico')
    c.setFont('Helvetica', 5)
    c.drawCentredString(x2 + 52.5, H - y - 50, 'MODAL')
    c.setFont('Helvetica-Bold', 8.5)
    c.drawCentredString(x2 + 52.5, H - y - 60, modal)
    c.setFont('Helvetica', 5)
    c.drawCentredString(x2 + 52.5, H - y - 76, 'TIPO DO CT-e')
    c.setFont('Helvetica-Bold', 7)
    c.drawCentredString(x2 + 52.5, H - y - 85, TP_CTE.get(_t(ide, 'tpCTe'), _t(ide, 'tpCTe')))
    # chave, código de barras e protocolo
    x3 = x2 + 105
    w3 = LW - 230 - 105
    D.caixa(x3, y, w3, 36)
    if len(chave) == 44:
        bc = code128.Code128(chave, barHeight=27, barWidth=0.6, humanReadable=False)
        bc.drawOn(c, x3 + (w3 - bc.width) / 2, H - y - 32)
    D.caixa(x3, y + 36, w3, 22, 'Chave de acesso', _chave_fmt(chave), tam=7, neg=True, alin='c')
    pdt, phr = _data(_t(prot, 'dhRecbto')) if prot is not None else ('', '')
    D.caixa(x3, y + 58, w3, 34, 'Protocolo de autorização de uso',
            f'{_t(prot, "nProt")}  {pdt} {phr}' if prot is not None else 'SEM PROTOCOLO DE AUTORIZAÇÃO', tam=7.5, neg=True, alin='c')
    c.setFont('Helvetica', 5.6)
    c.drawCentredString(x3 + w3 / 2, H - y - 72, 'Consulta em www.cte.fazenda.gov.br/portal')

    # identificação
    y += 96
    cols = [('Modelo', _t(ide, 'mod') or '57', 34), ('Série', _t(ide, 'serie'), 34), ('Número', num, 60),
            ('Data e hora de emissão', f'{dt} {hr}', 90), ('Tipo do serviço', TP_SERV.get(_t(ide, 'tpServ'), _t(ide, 'tpServ')), 120)]
    toma = inf.find('ide/toma3')
    if toma is None:
        toma = inf.find('ide/toma03')
    toma4 = inf.find('ide/toma4')
    toma_cod = _t(toma, 'toma') if toma is not None else ('4' if toma4 is not None else '')
    usado = sum(w for _, _, w in cols)
    cols.append(('Tomador do serviço', TOMA.get(toma_cod, toma_cod), LW - usado))
    x = M
    for rot, val, w in cols:
        D.caixa(x, y, w, 22, rot, val, tam=7.5, neg=True)
        x += w
    y += 22
    D.caixa(M, y, LW, 22, 'CFOP - natureza da operação', f'{_t(ide, "CFOP")} - {_t(ide, "natOp")}', tam=7.5)
    y += 22
    D.caixa(M, y, LW / 2, 22, 'Início da prestação', f'{_t(ide, "xMunIni")} - {_t(ide, "UFIni")}', tam=7.5)
    D.caixa(M + LW / 2, y, LW / 2, 22, 'Término da prestação', f'{_t(ide, "xMunFim")} - {_t(ide, "UFFim")}', tam=7.5)
    y += 26

    # participantes
    _participante(D, M, y, LW / 2, 46, 'Remetente', rem)
    _participante(D, M + LW / 2, y, LW / 2, 46, 'Destinatário', dest)
    y += 46
    _participante(D, M, y, LW / 2, 46, 'Expedidor', exped)
    _participante(D, M + LW / 2, y, LW / 2, 46, 'Recebedor', receb)
    y += 46
    if toma_cod == '4' and toma4 is not None:
        tno = toma4
    else:
        tno = {'0': rem, '1': exped, '2': receb, '3': dest}.get(toma_cod)
    _participante(D, M, y, LW, 46, 'Tomador do serviço', tno)
    y += 50

    # carga
    D.caixa(M, y, 230, 22, 'Produto predominante', _t(carga, 'proPred'), tam=7.5)
    D.caixa(M + 230, y, 160, 22, 'Outras características da carga', _t(carga, 'xOutCat'), tam=7.5)
    D.caixa(M + 390, y, LW - 390, 22, 'Valor total da carga', _m(_t(carga, 'vCarga')), tam=7.5, neg=True, alin='r')
    y += 22
    qs = carga.findall('infQ') if carga is not None else []
    wq = LW / 4
    for k in range(4):
        q = qs[k] if k < len(qs) else None
        rot = f'{_t(q, "tpMed") or "Quantidade"} ({UNID.get(_t(q, "cUnid"), "")})' if q is not None else 'Quantidade'
        D.caixa(M + k * wq, y, wq, 22, rot, _m(_t(q, 'qCarga'), 4) if q is not None else '', tam=7.5, alin='r')
    y += 26

    # componentes do valor
    D.titulo(M, y, 'Componentes do valor da prestação do serviço')
    y += 9
    comps = vprest.findall('Comp') if vprest is not None else []
    wc = (LW - 150) / 3
    linhas_c = max(2, -(-len(comps) // 3))
    for k in range(linhas_c * 3):
        cp = comps[k] if k < len(comps) else None
        col, lin = k % 3, k // 3
        D.caixa(M + col * wc, y + lin * 16, wc, 16, '', '')
        if cp is not None:
            c.setFont('Helvetica', 6.8)
            c.drawString(M + col * wc + 3, H - y - lin * 16 - 11, D.cabe(_t(cp, 'xNome'), 'Helvetica', 6.8, wc - 60))
            c.drawRightString(M + (col + 1) * wc - 3, H - y - lin * 16 - 11, _m(_t(cp, 'vComp')))
    hc = linhas_c * 16
    D.caixa(M + LW - 150, y, 150, hc / 2, 'Valor total do serviço', _m(_t(vprest, 'vTPrest')), tam=8.5, neg=True, alin='r')
    D.caixa(M + LW - 150, y + hc / 2, 150, hc / 2, 'Valor a receber', _m(_t(vprest, 'vRec')), tam=8.5, neg=True, alin='r')
    y += hc + 4

    # imposto
    D.titulo(M, y, 'Informações relativas ao imposto')
    y += 9
    icms = inf.find('imp/ICMS')
    g = list(icms)[0] if icms is not None and len(list(icms)) else None
    cst = _t(g, 'CST') or ('SN' if g is not None and 'SN' in g.tag else '')
    impc = [('Situação tributária', cst, 110), ('Base de cálculo', _m(_t(g, 'vBC') or _t(g, 'vBCOutraUF')), 95),
            ('Alíq. ICMS', _m(_t(g, 'pICMS') or _t(g, 'pICMSOutraUF')), 70), ('Valor do ICMS', _m(_t(g, 'vICMS') or _t(g, 'vICMSOutraUF')), 95),
            ('% Red. BC', _m(_t(g, 'pRedBC') or _t(g, 'pRedBCOutraUF')), 70)]
    usado = sum(w for _, _, w in impc)
    impc.append(('ICMS ST', _m(_t(g, 'vICMSSTRet')), LW - usado))
    x = M
    for rot, val, w in impc:
        D.caixa(x, y, w, 22, rot, val, tam=7.5, alin='l' if rot == 'Situação tributária' else 'r')
        x += w
    y += 26

    # documentos originários
    D.titulo(M, y, 'Documentos originários')
    y += 9
    docs = []
    if norm is not None:
        for n in norm.findall('infDoc/infNFe'):
            docs.append(('NF-e', _chave_fmt(_t(n, 'chave'))))
        for n in norm.findall('infDoc/infNF'):
            docs.append((f'NF {_t(n, "mod")}', f'Série {_t(n, "serie")} Nº {_t(n, "nDoc")} · {_m(_t(n, "vNF"))}'))
        for n in norm.findall('infDoc/infOutros'):
            docs.append((_t(n, 'tpDoc'), f'{_t(n, "descOutros")} {_t(n, "nDoc")}'))
    lin_d = max(3, min(14, -(-len(docs) // 2)))
    wd = LW / 2
    D.caixa(M, y, wd, lin_d * 10 + 10, 'Tipo · documento')
    D.caixa(M + wd, y, wd, lin_d * 10 + 10, 'Tipo · documento')
    c.setFont('Helvetica', 6.5)
    for k, (tp, txt) in enumerate(docs[:lin_d * 2]):
        col, lin = k // lin_d, k % lin_d
        c.drawString(M + col * wd + 3, H - y - 15 - lin * 10, D.cabe(f'{tp}   {txt}', 'Helvetica', 6.5, wd - 6))
    if len(docs) > lin_d * 2:
        c.drawRightString(M + LW - 3, H - y - lin_d * 10 - 7, f'+ {len(docs) - lin_d * 2} documento(s)')
    y += lin_d * 10 + 14

    # observações
    obs = ' '.join(x for x in (_t(inf, 'compl/xObs'), ' '.join(_t(o, 'xTexto') for o in inf.findall('compl/ObsCont'))) if x).strip()
    resto = H - M - y - 46
    h_obs = max(40, min(110, resto))
    D.caixa(M, y, LW, h_obs, 'Observações')
    D.linhas(M + 3, y + 15, LW - 6, obs, tam=6.5, max_l=int((h_obs - 12) // 8))
    y += h_obs

    # modal rodoviário
    rodo = norm.find('infModal/rodo') if norm is not None else None
    D.titulo(M, y + 3, f'Dados específicos do modal {modal.lower()}')
    D.caixa(M, y + 12, 160, 22, 'RNTRC da empresa', _t(rodo, 'RNTRC'), tam=7.5)
    D.caixa(M + 160, y + 12, LW - 160, 22, 'Informação', 'Este DACTE foi gerado pelo FiscoCont+ a partir do XML autorizado.', tam=6.5)

    if tarja:
        _tarja(c, tarja)
    c.showPage()
    c.save()
    return saida


def main_cli(argv):
    xml, saida = argv[0], argv[argv.index('--saida') + 1]
    with open(xml, encoding='utf-8', errors='replace') as fh:
        gerar_pdf(fh.read(), saida)
    return 0


if __name__ == '__main__':
    sys.exit(main_cli(sys.argv[1:]))

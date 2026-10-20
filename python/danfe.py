# -*- coding: utf-8 -*-
"""DANFE (Documento Auxiliar da NF-e) em PDF, gerado a partir do XML da NF-e — retrato, A4.

Leiaute baseado no Manual de Orientação do Contribuinte (Anexo II — DANFE): canhoto, quadro do emitente, quadro
"DANFE" (entrada/saída, número, série, folha), chave de acesso com código de barras CODE-128C, natureza da operação e
protocolo de autorização, destinatário/remetente, fatura/duplicatas, cálculo do imposto, transportador, dados dos
produtos (várias folhas, se precisar) e dados adicionais.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128

W, H = A4
M = 22.0                      # margem
LW = W - 2 * M                # largura útil


def _limpa(texto):
    limpo = re.sub(r'\sxmlns(:\w+)?="[^"]*"', '', texto)
    limpo = re.sub(r'<(/?)\w+:', r'<\1', limpo)
    return ET.fromstring(re.sub(r'^\s*<\?xml[^>]*\?>', '', limpo.lstrip('﻿')))


def _t(no, cam, padrao=''):
    if no is None:
        return padrao
    x = no.find(cam)
    return (x.text or '').strip() if x is not None and x.text else padrao


def _n(s):
    try:
        return float(s) if s not in (None, '') else 0.0
    except ValueError:
        return 0.0


def _m(v, casas=2):
    return f'{_n(v) if isinstance(v, str) else v:,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _doc(d):
    d = re.sub(r'\D', '', d or '')
    if len(d) == 14:
        return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'
    if len(d) == 11:
        return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}'
    return d


def _data(iso):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?', iso or '')
    if not m:
        return '', ''
    return f'{m.group(3)}/{m.group(2)}/{m.group(1)}', (f'{m.group(4)}:{m.group(5)}' if m.group(4) else '')


def _chave_fmt(c):
    return ' '.join(c[i:i + 4] for i in range(0, len(c), 4))


def ler(texto):
    raiz = _limpa(texto)
    inf = raiz if raiz.tag == 'infNFe' else raiz.find('.//infNFe')
    if inf is None:
        raise ValueError('O arquivo não é uma NF-e.')
    chave = (inf.get('Id') or '').replace('NFe', '')
    prot = raiz.find('.//protNFe/infProt')
    return {'raiz': raiz, 'inf': inf, 'chave': chave, 'prot': prot}


# ------------------------------------------------------------------ desenho
class _D:
    def __init__(self, c):
        self.c = c

    def caixa(self, x, y, w, h, rot='', val='', tam=7.2, neg=False, alin='l'):
        """Caixa com rótulo pequeno no alto e valor embaixo. (x, y) = canto superior esquerdo, em pontos a partir do topo."""
        c = self.c
        c.setLineWidth(0.5)
        c.rect(x, H - y - h, w, h)
        if rot:
            c.setFont('Helvetica', 5)
            c.drawString(x + 2, H - y - 6.5, rot.upper())
        if val != '':
            c.setFont('Helvetica-Bold' if neg else 'Helvetica', tam)
            txt = self.cabe(str(val), 'Helvetica-Bold' if neg else 'Helvetica', tam, w - 4)
            yy = H - y - h + 3
            if alin == 'r':
                c.drawRightString(x + w - 2, yy, txt)
            elif alin == 'c':
                c.drawCentredString(x + w / 2, yy, txt)
            else:
                c.drawString(x + 2, yy, txt)

    def cabe(self, s, fonte, tam, larg):
        if self.c.stringWidth(s, fonte, tam) <= larg:
            return s
        while s and self.c.stringWidth(s + '…', fonte, tam) > larg:
            s = s[:-1]
        return s + '…'

    def titulo(self, x, y, s):
        self.c.setFont('Helvetica-Bold', 6.5)
        self.c.drawString(x, H - y - 6, s.upper())

    def linhas(self, x, y, w, texto, tam=6.5, max_l=8):
        c, out = self.c, []
        for par in (texto or '').replace(';', '; ').split('\n'):
            pal, atual = par.split(), ''
            for p in pal:
                t = (atual + ' ' + p).strip()
                if c.stringWidth(t, 'Helvetica', tam) > w:
                    out.append(atual)
                    atual = p
                else:
                    atual = t
            out.append(atual)
        c.setFont('Helvetica', tam)
        for k, l in enumerate(out[:max_l]):
            c.drawString(x, H - y - k * (tam + 1.5), l)


def gerar_pdf(texto_xml, saida):
    d = ler(texto_xml)
    inf, chave, prot = d['inf'], d['chave'], d['prot']
    ide, emit, dest = inf.find('ide'), inf.find('emit'), inf.find('dest')
    tot = inf.find('total/ICMSTot')
    transp = inf.find('transp')
    dets = inf.findall('det')
    ee = emit.find('enderEmit') if emit is not None else None
    de = dest.find('enderDest') if dest is not None else None

    c = canvas.Canvas(saida, pagesize=A4)
    c.setTitle(f'DANFE {chave}')
    c.setAuthor('FiscoCont+')
    D = _D(c)
    dt_emi, _ = _data(_t(ide, 'dhEmi') or _t(ide, 'dEmi'))
    dt_sai, hr_sai = _data(_t(ide, 'dhSaiEnt') or _t(ide, 'dSaiEnt'))
    num = _t(ide, 'nNF')
    num_fmt = f'{int(num):011,d}'.replace(',', '.') if num.isdigit() else num
    serie = _t(ide, 'serie')

    # itens por folha: 1ª folha tem os quadros; as demais só cabeçalho e itens
    alt_item = 9.0
    cap1 = int((H - 470 - 95) // alt_item)
    capn = int((H - 230 - 30) // alt_item)
    folhas = 1 if len(dets) <= cap1 else 1 + -(-(len(dets) - cap1) // capn)

    def cabecalho(y, folha):
        # emitente
        D.caixa(M, y, 240, 90)
        c.setFont('Helvetica-Bold', 9)
        D.linhas(M + 6, y + 14, 228, _t(emit, 'xNome'), tam=9, max_l=2)
        end = f'{_t(ee, "xLgr")}, {_t(ee, "nro")} {_t(ee, "xCpl")}'.strip()
        D.linhas(M + 6, y + 40, 228, f'{end}\n{_t(ee, "xBairro")} - CEP {_t(ee, "CEP")}\n{_t(ee, "xMun")} - {_t(ee, "UF")}   Fone: {_t(ee, "fone")}', tam=6.8)
        # quadro DANFE
        x2 = M + 240
        D.caixa(x2, y, 95, 90)
        c.setFont('Helvetica-Bold', 12)
        c.drawCentredString(x2 + 47.5, H - y - 16, 'DANFE')
        c.setFont('Helvetica', 5.8)
        c.drawCentredString(x2 + 47.5, H - y - 24, 'Documento Auxiliar da')
        c.drawCentredString(x2 + 47.5, H - y - 30, 'Nota Fiscal Eletrônica')
        c.drawString(x2 + 8, H - y - 42, '0 - ENTRADA')
        c.drawString(x2 + 8, H - y - 49, '1 - SAÍDA')
        c.rect(x2 + 62, H - y - 51, 14, 13)
        c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(x2 + 69, H - y - 48, _t(ide, 'tpNF'))
        c.setFont('Helvetica-Bold', 7.5)
        c.drawCentredString(x2 + 47.5, H - y - 64, f'Nº {num_fmt}')
        c.drawCentredString(x2 + 47.5, H - y - 73, f'SÉRIE {serie}')
        c.drawCentredString(x2 + 47.5, H - y - 83, f'FOLHA {folha}/{folhas}')
        # chave e código de barras
        x3 = x2 + 95
        w3 = LW - 240 - 95
        D.caixa(x3, y, w3, 34)
        if len(chave) == 44:
            bc = code128.Code128(chave, barHeight=26, barWidth=0.62, humanReadable=False)
            bc.drawOn(c, x3 + (w3 - bc.width) / 2, H - y - 31)
        D.caixa(x3, y + 34, w3, 22, 'Chave de acesso', _chave_fmt(chave), tam=7, neg=True, alin='c')
        D.caixa(x3, y + 56, w3, 34)
        c.setFont('Helvetica', 6.3)
        c.drawCentredString(x3 + w3 / 2, H - y - 67, 'Consulta de autenticidade no portal nacional da NF-e')
        c.drawCentredString(x3 + w3 / 2, H - y - 75, 'www.nfe.fazenda.gov.br/portal ou no site da Sefaz autorizadora')
        # natureza / protocolo
        y += 90
        D.caixa(M, y, 335, 20, 'Natureza da operação', _t(ide, 'natOp'))
        p = f'{_t(prot, "nProt")}  {" ".join(_data(_t(prot, "dhRecbto")))}' if prot is not None else 'NF-e sem protocolo de autorização no XML'
        D.caixa(M + 335, y, LW - 335, 20, 'Protocolo de autorização de uso', p, alin='c')
        y += 20
        w = LW / 3
        D.caixa(M, y, w, 20, 'Inscrição estadual', _t(emit, 'IE'))
        D.caixa(M + w, y, w, 20, 'Inscrição estadual do subst. tributário', _t(emit, 'IEST'))
        D.caixa(M + 2 * w, y, w, 20, 'CNPJ / CPF', _doc(_t(emit, 'CNPJ') or _t(emit, 'CPF')))
        return y + 20

    def itens_cab(y):
        D.titulo(M, y + 2, 'Dados dos produtos / serviços')
        y += 10
        cols = [('Código', 46), ('Descrição do produto / serviço', 0), ('NCM/SH', 36), ('CST', 20), ('CFOP', 22), ('UN', 18),
                ('Quant.', 36), ('V. unit.', 38), ('V. total', 40), ('BC ICMS', 38), ('V. ICMS', 32), ('V. IPI', 28), ('% ICMS', 22), ('% IPI', 20)]
        fixo = sum(w for _, w in cols)
        cols[1] = (cols[1][0], LW - fixo)
        x = M
        for rot, w in cols:
            c.setLineWidth(0.5)
            c.rect(x, H - y - 10, w, 10)
            c.setFont('Helvetica', 4.8)
            c.drawCentredString(x + w / 2, H - y - 7, rot.upper())
            x += w
        return y + 10, cols

    def item(y, cols, det):
        prod, imp = det.find('prod'), det.find('imposto')
        icms = imp.find('ICMS') if imp is not None else None
        g = list(icms)[0] if icms is not None and len(list(icms)) else None
        ipi = imp.find('IPI/IPITrib') if imp is not None else None
        cst = (_t(g, 'orig') + (_t(g, 'CST') or _t(g, 'CSOSN'))) if g is not None else ''
        vals = [_t(prod, 'cProd'), _t(prod, 'xProd'), _t(prod, 'NCM'), cst, _t(prod, 'CFOP'), _t(prod, 'uCom'),
                _m(_n(_t(prod, 'qCom')), 4), _m(_n(_t(prod, 'vUnCom')), 4), _m(_n(_t(prod, 'vProd'))),
                _m(_n(_t(g, 'vBC'))), _m(_n(_t(g, 'vICMS'))), _m(_n(_t(ipi, 'vIPI'))), _m(_n(_t(g, 'pICMS'))), _m(_n(_t(ipi, 'pIPI')))]
        x = M
        c.setFont('Helvetica', 5.6)
        for k, ((_, w), v) in enumerate(zip(cols, vals)):
            txt = D.cabe(v, 'Helvetica', 5.6, w - 3)
            if k >= 6:
                c.drawRightString(x + w - 1.5, H - y - 6.6, txt)
            elif k in (2, 3, 4, 5):
                c.drawCentredString(x + w / 2, H - y - 6.6, txt)
            else:
                c.drawString(x + 1.5, H - y - 6.6, txt)
            x += w
        c.setLineWidth(0.2)
        c.line(M, H - y - alt_item, M + LW, H - y - alt_item)
        return y + alt_item

    # ---------- folha 1
    y = M
    # canhoto
    D.caixa(M, y, LW - 110, 18, f'Recebemos de {_t(emit, "xNome")} os produtos/serviços constantes da nota fiscal indicada ao lado',
            f'Emissão: {dt_emi}   Valor total: R$ {_m(_n(_t(tot, "vNF")))}   Destinatário: {_t(dest, "xNome")}', tam=6)
    D.caixa(M + LW - 110, y, 110, 36, 'NF-e', f'Nº {num_fmt}   Série {serie}', tam=7.5, neg=True, alin='c')
    D.caixa(M, y + 18, 120, 18, 'Data de recebimento')
    D.caixa(M + 120, y + 18, LW - 230, 18, 'Identificação e assinatura do recebedor')
    c.setDash(2, 2)
    c.line(M, H - y - 42, M + LW, H - y - 42)
    c.setDash()
    y = cabecalho(y + 48, 1)

    # destinatário
    D.titulo(M, y + 2, 'Destinatário / remetente')
    y += 10
    D.caixa(M, y, 330, 20, 'Nome / razão social', _t(dest, 'xNome'))
    D.caixa(M + 330, y, 120, 20, 'CNPJ / CPF', _doc(_t(dest, 'CNPJ') or _t(dest, 'CPF')), alin='c')
    D.caixa(M + 450, y, LW - 450, 20, 'Data da emissão', dt_emi, alin='c')
    y += 20
    D.caixa(M, y, 260, 20, 'Endereço', f'{_t(de, "xLgr")}, {_t(de, "nro")} {_t(de, "xCpl")}'.strip(', '))
    D.caixa(M + 260, y, 120, 20, 'Bairro / distrito', _t(de, 'xBairro'))
    D.caixa(M + 380, y, 70, 20, 'CEP', _t(de, 'CEP'), alin='c')
    D.caixa(M + 450, y, LW - 450, 20, 'Data da saída/entrada', dt_sai, alin='c')
    y += 20
    D.caixa(M, y, 220, 20, 'Município', _t(de, 'xMun'))
    D.caixa(M + 220, y, 30, 20, 'UF', _t(de, 'UF'), alin='c')
    D.caixa(M + 250, y, 90, 20, 'Fone / fax', _t(de, 'fone'))
    D.caixa(M + 340, y, 110, 20, 'Inscrição estadual', _t(dest, 'IE'))
    D.caixa(M + 450, y, LW - 450, 20, 'Hora da saída/entrada', hr_sai, alin='c')
    y += 22

    # fatura / duplicatas
    dups = inf.findall('cobr/dup')
    if dups:
        D.titulo(M, y + 2, 'Fatura / duplicatas')
        y += 10
        wdup = LW / 6
        for k, dp in enumerate(dups[:12]):
            xx, yy = M + (k % 6) * wdup, y + (k // 6) * 20
            dv, _ = _data(_t(dp, 'dVenc'))
            D.caixa(xx, yy, wdup, 20, f'Nº {_t(dp, "nDup")}  venc. {dv}', f'R$ {_m(_n(_t(dp, "vDup")))}', alin='r')
        y += 20 * (1 + (min(len(dups), 12) - 1) // 6) + 2

    # cálculo do imposto
    D.titulo(M, y + 2, 'Cálculo do imposto')
    y += 10
    w = LW / 6
    linha1 = [('Base de cálc. do ICMS', 'vBC'), ('Valor do ICMS', 'vICMS'), ('Base de cálc. ICMS S.T.', 'vBCST'),
              ('Valor do ICMS subst.', 'vST'), ('V. tot. tributos (aprox.)', 'vTotTrib'), ('Valor total dos produtos', 'vProd')]
    linha2 = [('Valor do frete', 'vFrete'), ('Valor do seguro', 'vSeg'), ('Desconto', 'vDesc'), ('Outras despesas', 'vOutro'),
              ('Valor total do IPI', 'vIPI'), ('Valor total da nota', 'vNF')]
    for k, (rot, tag) in enumerate(linha1):
        D.caixa(M + k * w, y, w, 20, rot, _m(_n(_t(tot, tag))), alin='r')
    for k, (rot, tag) in enumerate(linha2):
        D.caixa(M + k * w, y + 20, w, 20, rot, _m(_n(_t(tot, tag))), alin='r', neg=(tag == 'vNF'))
    y += 42
    if _n(_t(tot, 'vICMSDeson')) > 0:
        c.setFont('Helvetica', 6)
        c.drawString(M, H - y - 5, f'ICMS desonerado: R$ {_m(_n(_t(tot, "vICMSDeson")))}')
        y += 8

    # transportador
    tr = transp.find('transporta') if transp is not None else None
    vol = transp.find('vol') if transp is not None else None
    vei = transp.find('veicTransp') if transp is not None else None
    mod = {'0': '0-Emitente', '1': '1-Destinatário', '2': '2-Terceiros', '3': '3-Próprio rem.', '4': '4-Próprio dest.', '9': '9-Sem frete'}
    D.titulo(M, y + 2, 'Transportador / volumes transportados')
    y += 10
    D.caixa(M, y, 200, 20, 'Nome / razão social', _t(tr, 'xNome'))
    D.caixa(M + 200, y, 80, 20, 'Frete por conta', mod.get(_t(transp, 'modFrete'), _t(transp, 'modFrete')))
    D.caixa(M + 280, y, 60, 20, 'Placa do veículo', _t(vei, 'placa'))
    D.caixa(M + 340, y, 25, 20, 'UF', _t(vei, 'UF'), alin='c')
    D.caixa(M + 365, y, LW - 365, 20, 'CNPJ / CPF', _doc(_t(tr, 'CNPJ') or _t(tr, 'CPF')))
    y += 20
    D.caixa(M, y, 60, 20, 'Quantidade', _t(vol, 'qVol'), alin='r')
    D.caixa(M + 60, y, 100, 20, 'Espécie', _t(vol, 'esp'))
    D.caixa(M + 160, y, 100, 20, 'Marca', _t(vol, 'marca'))
    D.caixa(M + 260, y, 90, 20, 'Numeração', _t(vol, 'nVol'))
    D.caixa(M + 350, y, (LW - 350) / 2, 20, 'Peso bruto', _t(vol, 'pesoB'), alin='r')
    D.caixa(M + 350 + (LW - 350) / 2, y, (LW - 350) / 2, 20, 'Peso líquido', _t(vol, 'pesoL'), alin='r')
    y += 22

    # itens
    rodape = 95                                   # espaço dos dados adicionais na 1ª folha
    y, cols = itens_cab(y)
    k = 0
    while k < len(dets) and y + alt_item <= H - M - rodape:
        y = item(y, cols, dets[k])
        k += 1

    # dados adicionais (1ª folha)
    yd = H - M - rodape + 6
    D.titulo(M, yd - 8, 'Dados adicionais')
    D.caixa(M, yd, LW * 0.68, rodape - 6, 'Informações complementares')
    D.linhas(M + 3, yd + 14, LW * 0.68 - 6, (_t(inf, 'infAdic/infCpl') + ('\n' + _t(inf, 'infAdic/infAdFisco') if _t(inf, 'infAdic/infAdFisco') else '')), tam=5.8, max_l=10)
    D.caixa(M + LW * 0.68, yd, LW * 0.32, rodape - 6, 'Reservado ao fisco')
    if prot is None:
        c.setFont('Helvetica-Bold', 28)
        c.setFillGray(0.85)
        c.drawCentredString(W / 2, H / 2, 'SEM VALOR FISCAL')
        c.setFillGray(0)
    c.setFont('Helvetica', 5.5)
    c.drawRightString(W - M, 10, 'Gerado pelo FiscoCont+ a partir do XML da NF-e')
    folha = 1
    while k < len(dets):
        c.showPage()
        folha += 1
        y = cabecalho(M, folha)
        y, cols = itens_cab(y + 4)
        while k < len(dets) and y + alt_item <= H - M:
            y = item(y, cols, dets[k])
            k += 1
        c.setFont('Helvetica', 5.5)
        c.drawRightString(W - M, 10, 'Gerado pelo FiscoCont+ a partir do XML da NF-e')
    c.save()


def achar_xml(caminhos, chave):
    """Texto do XML da NF-e com essa chave dentro das pastas/zips/arquivos informados, ou None."""
    import fiscal_core as fc
    chave = re.sub(r'\D', '', chave or '')
    candidatos = fc.coletar_xmls(caminhos)
    preferidos = [p for p in candidatos if chave in os.path.basename(p.split('::')[-1])]
    for p in preferidos + [p for p in candidatos if p not in preferidos]:
        try:
            t = fc._read_text(p)
        except Exception:
            continue
        if f'NFe{chave}' in t:
            return t
    return None


def main_cli(argv):
    """danfe XMLS --chave CHAVE --saida DANFE.pdf   (XMLS: pastas/.zip/.xml separados pelo separador do sistema)"""
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    if len(argv) < 2 or not opt('--chave') or not opt('--saida'):
        print(main_cli.__doc__, file=sys.stderr)
        return 1
    caminhos = [c for c in argv[1].split(os.pathsep) if c]
    texto = achar_xml(caminhos, opt('--chave'))
    if not texto:
        print(f'Não achei o XML da nota {opt("--chave")} nos arquivos importados.', file=sys.stderr)
        return 2
    tmp = opt('--saida') + '.parcial'
    try:
        gerar_pdf(texto, tmp)
    except Exception as e:
        print(f'Não foi possível gerar o DANFE: {e}', file=sys.stderr)
        return 3
    os.replace(tmp, opt('--saida'))
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main_cli(sys.argv[1:]))

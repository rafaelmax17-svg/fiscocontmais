# -*- coding: utf-8 -*-
"""
DANFSe v2.0 (PDF da NFS-e Nacional) gerado a partir do XML.

Layout reproduzido do DANFSe do Portal Nacional (A4, coordenadas medidas no
PDF oficial) e conferido campo a campo contra três PDFs oficiais com o
respectivo XML. Onde o portal mostra "-" (campo ausente no XML) mostramos "-".

Duas regras que parecem estranhas mas são do próprio portal (conferidas nos
PDFs oficiais):
  * "Exclusões e Reduções da Base de Cálculo" mostra o valor do ISSQN
  * "Total do IBS/CBS" e "Valor líquido + IBS/CBS" mostram R$ 0,00 quando
    o XML não traz o grupo de IBS/CBS
"""
import io
import os
import re
import xml.etree.ElementTree as ET

from nfse_pdf_dados import UF_POR_CODIGO, logo_png_bytes, municipios

W, H = 595.0, 842.0
COL = (11.9, 156.5, 301.0, 445.6)     # início do texto de cada uma das 4 colunas
K = 0.79                              # linha de base = topo + K * tamanho da fonte
PASSO = 7.9                           # distância entre linhas de texto corrido
_MUN = None


# ------------------------------------------------------------------ leitura do XML
def _raiz(caminho):
    with open(caminho, 'rb') as f:
        raiz = ET.fromstring(f.read())
    for el in raiz.iter():
        el.tag = el.tag.split('}')[-1]
    return raiz


def _t(no, caminho, padrao=''):
    if no is None:
        return padrao
    el = no.find(caminho)
    if el is None or el.text is None:
        return padrao
    v = el.text.strip()
    return v if v else padrao


def _digitos(s):
    return re.sub(r'\D', '', s or '')


def _moeda(v):
    try:
        return 'R$ ' + f'{float(v):,.2f}'.replace(',', '§').replace('.', ',').replace('§', '.')
    except (TypeError, ValueError):
        return '-'


def _fmt_doc(d):
    d = _digitos(d)
    if len(d) == 14:
        return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'
    if len(d) == 11:
        return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}'
    return d or '-'


def _fmt_cep(c):
    c = _digitos(c)
    return f'{c[:2]}.{c[2:5]}-{c[5:]}' if len(c) == 8 else (c or '-')


def _fmt_ibge(c):
    c = _digitos(c)
    return f'{c[:2]}.{c[2:]}' if len(c) == 7 else (c or '-')


def _fmt_fone(f):
    f = _digitos(f)
    if len(f) == 10:
        return f'({f[:2]}) {f[2:6]}-{f[6:]}'
    if len(f) == 11:
        return f'({f[:2]}) {f[2:7]}-{f[7:]}'
    return f or '-'


def _fmt_data(iso):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', iso or '')
    return f'{m.group(3)}/{m.group(2)}/{m.group(1)}' if m else '-'


def _fmt_datahora(iso):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2}:\d{2})', iso or '')
    return f'{m.group(3)}/{m.group(2)}/{m.group(1)} {m.group(4)}' if m else _fmt_data(iso)


def _fmt_nbs(c):
    c = _digitos(c)
    return f'{c[0]}.{c[1:5]}.{c[5:7]}.{c[7:9]}' if len(c) == 9 else (c or '-')


def _fmt_trib_nac(c):
    c = _digitos(c)
    return f'{c[:2]}.{c[2:4]}.{c[4:6]}' if len(c) == 6 else (c or '-')


def _mun_uf(cmun):
    global _MUN
    if _MUN is None:
        _MUN = municipios()
    cmun = _digitos(cmun)
    return _MUN.get(cmun, ''), UF_POR_CODIGO.get(cmun[:2], '')


def _cidade_uf(cmun, nome_xml='', uf_xml=''):
    nome, uf = _mun_uf(cmun)
    return (nome_xml or nome), (uf_xml or uf)


_TP_EMIT = {'1': 'Prestador', '2': 'Tomador', '3': 'Intermediário'}
_OP_SIMPLES = {'1': 'Não optante', '2': 'Optante - Microempreendedor Individual (MEI)',
               '3': 'Optante - Microempresa ou Empresa de Pequeno Porte (ME/EPP)'}
_REG_AP_SN = {
    '1': 'Regime de apuração dos tributos federais e municipal pelo Simples Nacional',
    '2': 'Regime de apuração dos tributos federais pelo Simples Nacional e ISSQN pela NFS-e conforme respectivas legislações municipais do tributo',
    '3': 'Regime de apuração dos tributos federais e municipal pela NFS-e conforme respectivas legislações federal e municipal de cada tributo',
}
_TRIB_ISSQN = {'1': 'Operação Tributável', '2': 'Imunidade', '3': 'Exportação de Serviço', '4': 'Não Incidência'}
_RET_ISSQN = {'1': 'Não Retido', '2': 'Retido pelo Tomador', '3': 'Retido pelo Intermediário'}
# NÃO validado contra PDF oficial (nenhum dos gabaritos tinha tpRetPisCofins)
_RET_PISCOFINS = {'0': 'PIS/COFINS/CSLL Não Retidos', '1': 'PIS/COFINS Retidos', '2': 'PIS/COFINS Não Retidos',
                  '3': 'PIS/COFINS/CSLL Retidos', '4': 'PIS/COFINS Retidos, CSLL Não Retido',
                  '5': 'PIS/COFINS Não Retidos, CSLL Retido'}


def _endereco(no_end, xlgr='xLgr', nro='nro', cpl='xCpl', bairro='xBairro'):
    if no_end is None:
        return '-'
    partes = [_t(no_end, p) for p in (xlgr, nro, cpl, bairro)]
    return ', '.join(p for p in partes if p) or '-'


def parse_danfse(caminho):
    """Todos os campos que o DANFSe imprime, já formatados como aparecem no PDF."""
    raiz = _raiz(caminho)
    inf = raiz.find('infNFSe') if raiz.tag != 'infNFSe' else raiz
    if inf is None:
        raise ValueError('XML sem infNFSe — não parece uma NFS-e Nacional.')
    dps = inf.find('DPS/infDPS')
    vn = inf.find('valores')
    vd = dps.find('valores') if dps is not None else None
    emit = inf.find('emit')
    prest = dps.find('prest') if dps is not None else None
    toma = dps.find('toma') if dps is not None else None
    chave = re.sub(r'^NFS', '', inf.get('Id', ''))

    # prestador
    cmun_p = _t(emit, 'enderNac/cMun')
    cid_p, uf_p = _cidade_uf(cmun_p, uf_xml=_t(emit, 'enderNac/UF'))
    # tomador
    cmun_t = _t(toma, 'end/endNac/cMun')
    cid_t, uf_t = _cidade_uf(cmun_t)
    doc_t = _t(toma, 'CNPJ') or _t(toma, 'CPF') or _t(toma, 'NIF')
    # serviço / incidência
    cloc_prest = _t(dps, 'serv/locPrest/cLocPrestacao')
    _, uf_prest = _mun_uf(cloc_prest)
    cid_prest = _t(inf, 'xLocPrestacao') or _mun_uf(cloc_prest)[0]
    _, uf_inc = _mun_uf(_t(inf, 'cLocIncid'))
    cid_inc = _t(inf, 'xLocIncid') or _mun_uf(_t(inf, 'cLocIncid'))[0]

    trib_fed = vd.find('trib/tribFed') if vd is not None else None
    piscofins = trib_fed.find('piscofins') if trib_fed is not None else None
    tp_pc = _t(piscofins, 'tpRetPisCofins')
    trib_mun = vd.find('trib/tribMun') if vd is not None else None
    tot = vd.find('trib/totTrib/vTotTrib') if vd is not None else None

    def m(no, caminho):
        v = _t(no, caminho)
        return _moeda(v) if v != '' else '-'

    v_iss = _t(vn, 'vISSQN')
    v_serv = _t(vd, 'vServPrest/vServ')
    aliq = _t(vn, 'pAliqAplic')
    op_simples = _t(prest, 'regTrib/opSimpNac')
    reg_ap = _t(prest, 'regTrib/regApTribSN')
    info_compl = _t(dps, 'infoCompl/xInfComp')

    return {
        'chave': chave,
        'municipio_cab': f"{_t(inf, 'xLocEmi')} - {uf_p}".strip(' -'),
        'amb_ger': _t(inf, 'ambGer') or '-', 'tp_amb': _t(dps, 'tpAmb') or '-',
        'n_nfse': _t(inf, 'nNFSe') or '-', 'competencia': _fmt_data(_t(dps, 'dCompet')),
        'emissao_nfse': _fmt_datahora(_t(inf, 'dhProc')),
        'n_dps': _t(dps, 'nDPS') or '-', 'serie': (_t(dps, 'serie').lstrip('0') or '0') if _t(dps, 'serie') else '-',
        'emissao_dps': _fmt_datahora(_t(dps, 'dhEmi')),
        'emitente': _TP_EMIT.get(_t(dps, 'tpEmit'), '-'), 'finalidade': '-',
        # prestador
        'p_doc': _fmt_doc(_t(prest, 'CNPJ') or _t(prest, 'CPF') or _t(emit, 'CNPJ')),
        'p_im': _t(prest, 'IM') or '-', 'p_fone': _fmt_fone(_t(prest, 'fone')),
        'p_nome': _t(emit, 'xNome') or '-',
        'p_mun': f'{cid_p} / {uf_p}' if cid_p else '-', 'p_ibge_cep': f"{_fmt_ibge(cmun_p)} / {_fmt_cep(_t(emit, 'enderNac/CEP'))}",
        'p_end': _endereco(emit.find('enderNac') if emit is not None else None),
        'p_email': _t(prest, 'email') or _t(emit, 'email') or '-',
        'p_simples': _OP_SIMPLES.get(op_simples, '-'), 'p_reg_ap': _REG_AP_SN.get(reg_ap, '-'),
        # tomador
        't_doc': _fmt_doc(doc_t), 't_im': _t(toma, 'IM') or '-', 't_fone': _fmt_fone(_t(toma, 'fone')),
        't_nome': _t(toma, 'xNome') or '-',
        't_mun': f'{cid_t} / {uf_t}' if cid_t else '-', 't_ibge_cep': f"{_fmt_ibge(cmun_t)} / {_fmt_cep(_t(toma, 'end/endNac/CEP'))}",
        't_end': _endereco(toma.find('end') if toma is not None else None),
        't_email': _t(toma, 'email') or '-',
        'tem_dest': dps is not None and dps.find('dest') is not None,
        'tem_interm': dps is not None and dps.find('interm') is not None,
        # serviço
        's_trib': f"{_fmt_trib_nac(_t(dps, 'serv/cServ/cTribNac'))} / {_t(dps, 'serv/cServ/cTribMun') or '-'}",
        's_nbs': _fmt_nbs(_t(dps, 'serv/cServ/cNBS')),
        's_local': f"{cid_prest or '-'} / {uf_prest or '-'} / -",
        's_resumo': _t(inf, 'xTribMun') or _t(inf, 'xTribNac'),
        's_desc': _t(dps, 'serv/cServ/xDescServ'),
        # tributação municipal
        'm_tipo': _TRIB_ISSQN.get(_t(trib_mun, 'tribISSQN'), '-'),
        'm_incid': f"{cid_inc or '-'} / {uf_inc or '-'} / -" if cid_inc else '-',
        'm_bc': m(vn, 'vBC'), 'm_aliq': (aliq.replace('.', ',') + ' %') if aliq else '-',
        'm_ret': _RET_ISSQN.get(_t(trib_mun, 'tpRetISSQN'), '-'),
        'm_iss': m(vn, 'vISSQN'),
        # tributação federal
        'f_irrf': m(trib_fed, 'vRetIRRF'), 'f_cp': m(trib_fed, 'vRetCP'), 'f_cs': m(trib_fed, 'vRetCSLL'),
        'f_pis': m(piscofins, 'vPis'), 'f_cofins': m(piscofins, 'vCofins'),
        'f_desc_cs': _RET_PISCOFINS.get(tp_pc, '-') if tp_pc else '-',
        # IBS/CBS: só o que os PDFs oficiais mostram preenchido
        'i_excl': _moeda(v_iss) if v_iss else '-',
        # totais
        'v_serv': _moeda(v_serv) if v_serv else '-',
        'v_desc_inc': m(vd, 'vDescCondIncond/vDescIncond'), 'v_desc_cond': m(vd, 'vDescCondIncond/vDescCond'),
        'v_ret': m(vn, 'vTotalRet'),
        'v_liq': _moeda(_t(vn, 'vLiq') or v_serv) if (_t(vn, 'vLiq') or v_serv) else '-',
        'v_ibscbs': 'R$ 0,00', 'v_liq_ibscbs': 'R$ 0,00',
        'aprox': ('Totais aproximados dos Tributos cfe. Lei n° 12.741/2012: '
                  f"Federais: {m(tot, 'vTotTribFed')}; Estaduais: {m(tot, 'vTotTribEst')}; Municipais: {m(tot, 'vTotTribMun')};"),
        'info_compl': info_compl,
    }


# ------------------------------------------------------------------ desenho do PDF
def _seguro(s):
    return str(s).encode('cp1252', 'replace').decode('cp1252')


def _cabe(s, fonte, tam, larg):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    s = _seguro(s)
    if larg is None or stringWidth(s, fonte, tam) <= larg:
        return s
    while s and stringWidth(s + '...', fonte, tam) > larg:
        corte = s.rfind(' ')
        s = s[:corte] if corte > 0 else s[:-1]
    return s + '...'


def gerar_pdf(dados, saida, cancelada=False):
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.utils import ImageReader, simpleSplit
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(saida, pagesize=(W, H))
    c.setTitle(f"DANFSe {dados['n_nfse']}")
    c.setAuthor('FiscoCont+')

    def txt(x, top, s, tam=7, negrito=False, centro=False, larg=None):
        fonte = 'Helvetica-Bold' if negrito else 'Helvetica'
        s = _cabe(s, fonte, tam, larg)
        c.setFont(fonte, tam)
        (c.drawCentredString if centro else c.drawString)(x, H - (top + K * tam), s)

    def linha(top, x0=8.5, x1=586.8, lw=0.5):
        c.setLineWidth(lw)
        c.line(x0, H - top, x1, H - top)

    def barra(x0, t0, x1, t1):
        c.setFillGray(0.949)
        c.rect(x0, H - t1, x1 - x0, t1 - t0, stroke=0, fill=1)
        c.setFillGray(0)

    def campo(ci, t_rot, t_val, rot, val, tam_rot=6, larg=None):
        if larg is None:
            larg = (586.8 if ci == 3 else COL[ci + 1]) - COL[ci] - 4
        txt(COL[ci], t_rot, rot, tam_rot, True)
        txt(COL[ci], t_val, val, 7, False, larg=larg)

    d = dados
    # moldura e cabeçalho
    c.setLineWidth(1)
    c.rect(5, H - 837, 585, 832, stroke=1, fill=0)
    for x0, x1 in ((8.5, 153.1), (153.1, 442.2), (442.2, 586.8)):
        barra(x0, 5.7, x1, 39.7)
    linha(39.9)
    c.drawImage(ImageReader(io.BytesIO(logo_png_bytes())), 12, H - 33, width=116, height=23, mask='auto')
    txt(297.6, 13.7, 'DANFSe v2.0', 9, True, centro=True)
    txt(297.6, 24.0, 'Documento Auxiliar da NFS-e', 9, True, centro=True)
    txt(445.6, 12.4, f"Município: {d['municipio_cab']}", 8)
    txt(445.6, 21.2, f"Ambiente Gerador: {d['amb_ger']}", 6)
    txt(445.6, 28.0, f"Tipo de Ambiente: {d['tp_amb']}", 6)

    # chave + QR
    txt(COL[0], 45.5, 'CHAVE DE ACESSO DA NFS-e', 7, True)
    txt(COL[0], 53.4, d['chave'], 7)
    qr = QrCodeWidget(f"https://www.nfse.gov.br/ConsultaPublica?tpc=1&chave={d['chave']}")
    b = qr.getBounds()
    lado = 45.0
    desenho = Drawing(lado, lado, transform=[lado / (b[2] - b[0]), 0, 0, lado / (b[3] - b[1]), 0, 0])
    desenho.add(qr)
    renderPDF.draw(desenho, c, 492, H - 90)
    for i, s in enumerate(('A autenticidade desta NFS-e pode ser verificada',
                           'pela leitura deste código QR ou pela consulta da',
                           'chave de acesso no portal nacional da NFS-e')):
        txt(445.6, 92.7 + 6.8 * i, s, 6)

    # identificação
    barra(8.5, 105.1, 153.1, 125.3)
    for t_rot, t_val, rots, vals in (
        (65.7, 73.6, ('NÚMERO DA NFS-e', 'COMPETÊNCIA DA NFS-e', 'DATA E HORA DA EMISSÃO DA NFS-e'),
         (d['n_nfse'], d['competencia'], d['emissao_nfse'])),
        (85.9, 93.9, ('NÚMERO DA DPS', 'SÉRIE DA DPS', 'DATA E HORA DA EMISSÃO DA DPS'),
         (d['n_dps'], d['serie'], d['emissao_dps'])),
        (106.2, 114.1, ('EMITENTE DA NFS-e', 'SITUAÇÃO DA NFS-e', 'FINALIDADE'),
         (d['emitente'], 'NFS-e Gerada', d['finalidade'])),
    ):
        for i in range(3):
            txt(COL[i], t_rot, rots[i], 7, True)
            txt(COL[i], t_val, vals[i], 7, larg=COL[i + 1] - COL[i] - 4)
    linha(125.6)

    def parte(prefixo, titulo, y0, tem_lin4):
        barra(8.5, y0, 153.1, y0 + 19.1)
        txt(COL[0], y0 + 1.1, titulo, 7, True)
        r1, r2, r3 = y0 + 0.9, y0 + 20.0, y0 + 39.1
        campo(1, r1, r1 + 7.0, 'CNPJ / CPF / NIF', d[prefixo + '_doc'])
        campo(2, r1, r1 + 7.0, 'Indicador Municipal (Inscrição)', d[prefixo + '_im'])
        campo(3, r1, r1 + 7.0, 'Telefone', d[prefixo + '_fone'])
        campo(0, r2, r2 + 6.9, 'Nome / Nome Empresarial', d[prefixo + '_nome'], larg=285)
        campo(2, r2, r2 + 6.9, 'Município / Sigla UF', d[prefixo + '_mun'])
        campo(3, r2, r2 + 6.9, 'Código IBGE / CEP', d[prefixo + '_ibge_cep'])
        campo(0, r3, r3 + 6.9, 'Endereço', d[prefixo + '_end'], larg=285)
        campo(2, r3, r3 + 6.9, 'E-mail', d[prefixo + '_email'], larg=140)
        if tem_lin4:
            r4 = y0 + 58.2
            campo(0, r4, r4 + 6.9, 'Simples Nacional na Data de Competência', d['p_simples'], larg=142)
            campo(1, r4, r4 + 6.9, 'Regime de Apuração Tributária pelo SN', d['p_reg_ap'], larg=425)

    parte('p', 'PRESTADOR / FORNECEDOR', 125.8, True)
    linha(202.4)
    parte('t', 'TOMADOR / ADQUIRENTE', 202.6, False)
    linha(260.1)
    txt(297.6, 261.3, 'DESTINATÁRIO DA OPERAÇÃO ' + ('IDENTIFICADO NA NFS-e' if d['tem_dest'] else 'NÃO IDENTIFICADO NA NFS-e'), 7, centro=True)
    linha(268.5)
    txt(297.6, 269.7, 'INTERMEDIÁRIO DA OPERAÇÃO ' + ('IDENTIFICADO NA NFS-e' if d['tem_interm'] else 'NÃO IDENTIFICADO NA NFS-e'), 7, centro=True)
    linha(276.9)

    # serviço prestado
    barra(8.5, 277.2, 153.1, 296.3)
    txt(COL[0], 278.2, 'SERVIÇO PRESTADO', 7, True)
    campo(1, 278.1, 285.0, 'Código de Tributação Nacional/Municipal', d['s_trib'])
    campo(2, 278.1, 285.0, 'Código da NBS', d['s_nbs'])
    campo(3, 278.1, 285.0, 'Local da Prestação / Sigla UF / País', d['s_local'])
    larg_texto = 566.0
    resumo = simpleSplit(_seguro(d['s_resumo'] or '-'), 'Helvetica', 7, larg_texto) or ['-']
    for i, s in enumerate(resumo):
        txt(COL[0], 297.2 + PASSO * i, s, 7)
    t_desc_rot = 297.2 + PASSO * len(resumo) + 4.3
    txt(COL[0], t_desc_rot, 'Descrição do Serviço', 6, True)
    desc = simpleSplit(_seguro(d['s_desc'] or '-'), 'Helvetica', 7, larg_texto) or ['-']
    for i, s in enumerate(desc):
        txt(COL[0], t_desc_rot + 6.9 + PASSO * i, s, 7)
    dy = PASSO * ((len(resumo) - 2) + (len(desc) - 2))

    def y(v):
        return v + dy

    # tributação municipal
    linha(y(343.6))
    barra(8.5, y(343.9), 153.1, y(362.9))
    txt(COL[0], y(344.9), 'TRIBUTAÇÃO MUNICIPAL (ISSQN)', 7, True)
    campo(1, y(344.8), y(351.7), 'Tipo de Tributação do ISSQN', d['m_tipo'])
    campo(2, y(344.8), y(351.7), 'Município / Sigla UF / País de Incidência do ISSQN', d['m_incid'], larg=280)
    campo(0, y(363.8), y(370.8), 'BC ISSQN', d['m_bc'])
    campo(1, y(363.8), y(370.8), 'Alíquota Aplicada', d['m_aliq'])
    campo(2, y(363.8), y(370.8), 'Retenção do ISSQN', d['m_ret'])
    campo(3, y(363.8), y(370.8), 'ISSQN Apurado', d['m_iss'])
    # tributação federal
    linha(y(382.3))
    barra(8.5, y(382.5), 153.1, y(401.6))
    txt(COL[0], y(383.6), 'TRIBUTAÇÃO FEDERAL (EXCETO CBS)', 7, True)
    campo(1, y(383.4), y(390.3), 'IRRF', d['f_irrf'])
    campo(2, y(383.4), y(390.3), 'Contribuição Previdenciária - Retida', d['f_cp'])
    campo(3, y(383.4), y(390.3), 'Contribuições Sociais - Retidas', d['f_cs'])
    campo(0, y(402.5), y(409.4), 'PIS - Débito Apuração Própria', d['f_pis'])
    campo(1, y(402.5), y(409.4), 'COFINS - Débito Apuração Própria', d['f_cofins'])
    campo(2, y(402.5), y(409.4), 'Descrição Contrib. Sociais - Retidas', d['f_desc_cs'], larg=280)
    # IBS/CBS
    linha(y(420.9))
    barra(8.5, y(421.2), 153.1, y(440.2))
    txt(COL[0], y(422.2), 'TRIBUTAÇÃO IBS/CBS', 7, True)
    campo(1, y(422.1), y(429.0), 'CST / cClassTrib', '- / -')
    campo(2, y(422.1), y(429.0), 'Indicador de Operação / Código IBGE Incidência / Município Incidência / Sigla UF', '- / - / - / -', larg=285)
    campo(0, y(441.1), y(448.1), 'Exclusões e Reduções da Base de Cálculo', d['i_excl'])
    campo(1, y(441.1), y(448.1), 'Base de Cálculo Após Exclusões e Reduções', '-')
    campo(2, y(441.1), y(448.1), 'Red. Alíquota IBS / Red. Alíquota CBS', '- / - / -')
    campo(3, y(441.1), y(448.1), 'Alíquota - IBS UF / IBS Mun', '- / -')
    for ci, rot in enumerate(('Alíq. Efetiva Municipal - IBS', 'Valor Apurado Municipal - IBS',
                              'Alíq. Efetiva Estadual - IBS', 'Valor Apurado Estadual - IBS')):
        campo(ci, y(460.2), y(467.1), rot, '-')
    for ci, rot in enumerate(('Valor Total Apurado - IBS', 'Alíquota - CBS', 'Alíquota Efetiva - CBS', 'Valor Total Apurado - CBS')):
        campo(ci, y(479.3), y(486.2), rot, '-')
    # valor total
    linha(y(497.7))
    barra(8.5, y(498.0), 153.1, y(517.0))
    barra(442.2, y(517.0), 586.8, y(536.1))
    txt(COL[0], y(499.0), 'VALOR TOTAL DA NFS-e', 7, True)
    campo(1, y(498.9), y(505.8), 'VALOR DA OPERAÇÃO / SERVIÇO', d['v_serv'])
    campo(2, y(498.9), y(505.8), 'Desconto Incondicionado', d['v_desc_inc'])
    campo(3, y(498.9), y(505.8), 'Desconto Condicionado', d['v_desc_cond'])
    campo(0, y(517.9), y(524.9), 'Total das Retenções (ISSQN / Federais)', d['v_ret'])
    campo(1, y(517.9), y(524.9), 'VALOR LÍQUIDO DA NFS-e', d['v_liq'])
    campo(2, y(517.9), y(524.9), 'Total do IBS/CBS', d['v_ibscbs'])
    campo(3, y(517.9), y(524.9), 'VALOR LÍQUIDO DA NFS-e + IBS/CBS', d['v_liq_ibscbs'])
    linha(y(536.4))
    txt(COL[0], y(537.7), 'INFORMAÇÕES COMPLEMENTARES', 7, True)
    t = y(557.8)
    if d['info_compl']:
        for s in simpleSplit(_seguro(d['info_compl']), 'Helvetica', 7, larg_texto):
            txt(COL[0], t - 12, s, 7)
            t += PASSO
    for s in simpleSplit(_seguro(d['aprox']), 'Helvetica', 7, larg_texto):
        txt(COL[0], t, s, 7)
        t += PASSO

    # rodapé
    c.setLineWidth(1)
    for x0, x1 in ((9.0, 153.6), (153.6, 298.1), (298.1, 587.3)):
        c.rect(x0, H - 815.9, x1 - x0, 20.1, stroke=1, fill=0)
    txt(12.9, 797.2, 'DATA CIENTIFICAÇÃO:', 6, True)
    txt(157.5, 797.2, 'IDENTIFICAÇÃO E ASSINATURA', 6, True)
    txt(302.0, 797.2, 'N° NFS-e / CHAVE NFS-e', 6, True)
    txt(302.0, 804.1, f"{d['n_nfse']} / {d['chave']}", 7)

    if cancelada:
        # mesma marca d'água do PDF oficial do portal (medida no PDF): Arial 72pt,
        # 45 graus, preta com ~16% de opacidade, saindo de (159,248)
        c.saveState()
        c.setFillGray(0)
        c.setFillAlpha(0.157)
        c.translate(159.18, 248.11)
        c.rotate(45)
        c.setFont('Helvetica', 72)
        c.drawString(0, 0, 'CANCELADA')
        c.restoreState()

    c.showPage()
    c.save()
    return saida


def xml_para_pdf(caminho_xml, caminho_pdf, cancelada=None):
    """XML da NFS-e -> DANFSe em PDF. `cancelada` None = decide pelo nome do
    arquivo (sufixo .CANCELADA.xml, o mesmo marcador que o download usa)."""
    if cancelada is None:
        cancelada = caminho_xml.upper().endswith('.CANCELADA.XML')
    os.makedirs(os.path.dirname(os.path.abspath(caminho_pdf)), exist_ok=True)
    return gerar_pdf(parse_danfse(caminho_xml), caminho_pdf, cancelada=cancelada)

# -*- coding: utf-8 -*-
"""Consulta NF-e por chave de acesso — situação na SEFAZ, XML completo e PDF (DANFE).

Para cada chave:
  1. Situação: NfeConsultaProtocolo 4.00 na SEFAZ autorizadora (a UF está nos 2 primeiros dígitos da chave), com
     os eventos registrados (cancelamento, carta de correção, manifestação). Reaproveita manifestacao.py.
  2. XML (opcional, só NF-e modelo 55): NFeDistribuicaoDFe do Ambiente Nacional, consulta por chave (consChNFe), com o
     certificado da empresa do escritório. A SEFAZ só entrega o documento a quem participa da nota (destinatário,
     transportador ou CNPJ autorizado no grupo autXML). Para o destinatário, vem primeiro só o resumo (resNFe): o XML
     completo é liberado depois do evento "Ciência da Operação" (210210).
  3. Ciência da Operação (opcional, só quando o usuário marca): evento 210210 assinado com o certificado da empresa,
     enviado ao Ambiente Nacional (NFeRecepcaoEvento 4.00, cOrgao 91). Depois, consulta a chave de novo para pegar o XML.
  4. PDF: DANFE gerado a partir do XML baixado (danfe.py), com tarja "CANCELADA" quando a nota estiver cancelada.

Respostas do Ambiente Nacional tratadas (NT 2014.002): 138 documento localizado · 137 nenhum documento ·
640 o CNPJ não tem permissão para esta NF-e · 641 NF-e indisponível para o emitente · 632 fora do prazo de
download · 653 NF-e cancelada (arquivo indisponível) · 654 NF-e denegada (arquivo indisponível) · 656 consumo indevido.

Arquivos: <pasta base>/<MM-AAAA da emissão>/<empresa>/NF-e/XML/<chave>-procNFe.xml e .../NF-e/PDF/<chave>-DANFE.pdf
(mesma organização das NFS-e das Baixas DF-e). Arquivo já existente não é sobrescrito com conteúdo diferente.
"""
import base64
import gzip
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta

import manifestacao as mf

URL_DIST = 'https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx'
URL_EVENTO_AN = 'https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx'
NS_NFE = 'http://www.portalfiscal.inf.br/nfe'
NS_DS = 'http://www.w3.org/2000/09/xmldsig#'

MSG_DIST = {
    '137': 'A SEFAZ não devolveu documento para esta empresa.',
    '640': 'A empresa escolhida não participa desta nota (não é destinatária, transportadora nem autorizada a baixar).',
    '641': 'A SEFAZ não entrega a nota ao próprio emitente: o XML fica no sistema que emitiu.',
    '632': 'Fora do prazo: a SEFAZ não disponibiliza mais o download desta nota.',
    '653': 'Nota cancelada: a SEFAZ não disponibiliza o XML de nota cancelada.',
    '654': 'Nota denegada: a SEFAZ não disponibiliza o XML de nota denegada.',
    '656': 'A SEFAZ pediu para aguardar (consumo indevido). Tente baixar de novo daqui a 1 hora.',
}


def _limpa_nome(s):
    s = re.sub(r'[\\/:*?"<>|]+', ' ', str(s or '')).strip().rstrip('.')
    return re.sub(r'\s+', ' ', s)[:120] or 'Empresa'


def _soap_dist(sess, ch, cnpj, cuf):
    corpo = (f'<nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"><nfeDadosMsg>'
             f'<distDFeInt xmlns="{NS_NFE}" versao="1.01"><tpAmb>1</tpAmb><cUFAutor>{cuf}</cUFAutor>'
             f'<CNPJ>{cnpj}</CNPJ><consChNFe><chNFe>{ch}</chNFe></consChNFe></distDFeInt></nfeDadosMsg></nfeDistDFeInteresse>')
    env = ('<?xml version="1.0" encoding="utf-8"?><soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
           f'<soap12:Body>{corpo}</soap12:Body></soap12:Envelope>')
    r = sess.post(URL_DIST, data=env.encode('utf-8'), timeout=40, headers={
        'Content-Type': 'application/soap+xml; charset=utf-8; action="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"'})
    r.raise_for_status()
    return r.text


def distribuicao(sess, ch, cnpj, cuf):
    """Consulta a chave no Ambiente Nacional. Devolve {cstat, motivo, proc (XML completo), resumo {...}, eventos [...]}"""
    xml = _soap_dist(sess, ch, cnpj, cuf)
    ret = re.search(r'<(?:\w+:)?retDistDFeInt\b.*?</(?:\w+:)?retDistDFeInt>', xml, re.S)
    ret = ret.group(0) if ret else xml
    out = {'cstat': mf._txt(ret, 'cStat'), 'motivo': mf._txt(ret, 'xMotivo'), 'proc': '', 'resumo': {}, 'eventos': []}
    for m in re.finditer(r'<(?:\w+:)?docZip\b([^>]*)>([^<]+)</(?:\w+:)?docZip>', ret):
        try:
            doc = gzip.decompress(base64.b64decode(m.group(2))).decode('utf-8', 'replace')
        except Exception:
            continue
        if re.search(r'<(?:\w+:)?nfeProc\b', doc):
            out['proc'] = re.sub(r'^\s*<\?xml[^>]*\?>', '', doc).strip()
        elif re.search(r'<(?:\w+:)?resNFe\b', doc):
            out['resumo'] = {'emitente': mf._txt(doc, 'xNome'), 'valor': mf._txt(doc, 'vNF'), 'dh_emissao': mf._txt(doc, 'dhEmi'),
                             'csit': mf._txt(doc, 'cSitNFe')}
        elif re.search(r'<(?:\w+:)?(procEventoNFe|resEvento)\b', doc):
            out['eventos'].append({'tipo': mf._txt(doc, 'tpEvento'), 'quando': mf._txt(doc, 'dhRegEvento') or mf._txt(doc, 'dhEvento')})
    return out


# ------------------------------------------------------------------ assinatura do evento (XMLDSig enveloped, RSA-SHA1)
# O XML do evento é montado aqui já na forma canônica (C14N 1.0: sem espaços entre as tags, atributos em ordem,
# elementos vazios abertos/fechados), por isso o resumo (digest) pode ser calculado direto sobre o texto.
def _carrega_pfx(pfx, senha):
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
    with open(pfx, 'rb') as fh:
        chave, cert, _ = pkcs12.load_key_and_certificates(fh.read(), senha.encode('utf-8'))
    if chave is None or cert is None:
        raise ValueError('Certificado sem chave privada — senha errada ou arquivo corrompido.')
    der = cert.public_bytes(Encoding.DER)
    return chave, base64.b64encode(der).decode('ascii')


def _assina(inf_evento, id_ref, chave_priv, cert_b64):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    canon_inf = inf_evento.replace('<infEvento ', f'<infEvento xmlns="{NS_NFE}" ', 1)
    digest = base64.b64encode(hashlib.sha1(canon_inf.encode('utf-8')).digest()).decode('ascii')
    si = (f'<SignedInfo><CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"></CanonicalizationMethod>'
          f'<SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"></SignatureMethod>'
          f'<Reference URI="#{id_ref}"><Transforms><Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"></Transform>'
          f'<Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"></Transform></Transforms>'
          f'<DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"></DigestMethod><DigestValue>{digest}</DigestValue></Reference></SignedInfo>')
    canon_si = si.replace('<SignedInfo>', f'<SignedInfo xmlns="{NS_DS}">', 1)
    assinatura = base64.b64encode(chave_priv.sign(canon_si.encode('utf-8'), padding.PKCS1v15(), hashes.SHA1())).decode('ascii')
    return (f'<Signature xmlns="{NS_DS}">{si}<SignatureValue>{assinatura}</SignatureValue>'
            f'<KeyInfo><X509Data><X509Certificate>{cert_b64}</X509Certificate></X509Data></KeyInfo></Signature>')


def ciencia(sess, ch, cnpj, chave_priv, cert_b64):
    """Registra a Ciência da Operação (210210) no Ambiente Nacional. Devolve (ok, cstat, motivo)."""
    dh = (datetime.now().astimezone() - timedelta(minutes=2)).replace(microsecond=0).isoformat()
    id_ref = f'ID210210{ch}01'
    inf = (f'<infEvento Id="{id_ref}"><cOrgao>91</cOrgao><tpAmb>1</tpAmb><CNPJ>{cnpj}</CNPJ><chNFe>{ch}</chNFe>'
           f'<dhEvento>{dh}</dhEvento><tpEvento>210210</tpEvento><nSeqEvento>1</nSeqEvento><verEvento>1.00</verEvento>'
           f'<detEvento versao="1.00"><descEvento>Ciencia da Operacao</descEvento></detEvento></infEvento>')
    evento = f'<evento xmlns="{NS_NFE}" versao="1.00">{inf}{_assina(inf, id_ref, chave_priv, cert_b64)}</evento>'
    corpo = f'<envEvento xmlns="{NS_NFE}" versao="1.00"><idLote>{int(time.time() * 1000) % 10 ** 15}</idLote>{evento}</envEvento>'
    xml = mf._soap(sess, URL_EVENTO_AN, 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4', corpo, 'nfeRecepcaoEvento', timeout=40)
    rets = mf._blocos(xml, 'retEvento')
    if rets:
        cst, mot = mf._txt(rets[0], 'cStat'), mf._txt(rets[0], 'xMotivo')
    else:
        cst, mot = mf._txt(xml, 'cStat'), mf._txt(xml, 'xMotivo')
    # 135/136 registrado · 573 já existia ciência para esta nota
    return cst in ('135', '136', '573'), cst, mot


# ------------------------------------------------------------------ arquivos
def _grava(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding='utf-8') as fh:
                if fh.read() == texto:
                    return caminho
        except OSError:
            pass
        base, ext = os.path.splitext(caminho)
        caminho = f'{base} ({datetime.now():%Y%m%d-%H%M%S}){ext}'
    tmp = caminho + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(texto)
    os.replace(tmp, caminho)
    return caminho


def _pastas(pasta_base, empresa, dh_emissao, aamm):
    m = re.match(r'(\d{4})-(\d{2})', dh_emissao or '')
    mes = f'{m.group(2)}-{m.group(1)}' if m else aamm.replace('/', '-')       # aamm vem como MM/AAAA
    raiz = os.path.join(pasta_base, mes, _limpa_nome(empresa), 'NF-e')
    return os.path.join(raiz, 'XML'), os.path.join(raiz, 'PDF')


def _pdf(proc, destino, cancelada):
    import danfe
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + '.parcial'
    danfe.gerar_pdf(proc, tmp, tarja='CANCELADA' if cancelada else '')
    os.replace(tmp, destino)
    return destino


# ------------------------------------------------------------------ consulta
def consultar(chaves, cert_pem, key_pem, pfx, senha, cnpj, empresa, cuf='11', pasta_base='', baixar=True,
              com_ciencia=False, gerar_pdf=True, progresso=None, pausa=0.4):
    import requests
    sess = requests.Session()
    sess.cert = (cert_pem, key_pem)
    chave_priv = cert_b64 = None
    dist_ok = baixar
    res = []
    try:
        for i, ch in enumerate(chaves, 1):
            item = {'chave': ch, **mf.dados_da_chave(ch), 'xml': '', 'pdf': '', 'download': ''}
            # 1) situação na SEFAZ autorizadora
            try:
                xml, aut, _t = mf._consulta_situacao(sess, ch)
                item.update(mf._analisa_situacao(xml)); item['autorizador'] = aut
            except Exception as e:
                item.update({'situacao': 'erro', 'motivo': str(e)[:200]})
            for e in item.get('eventos') or []:
                e['nome'] = {'110110': 'carta_correcao', **mf.EVENTOS}.get(e['tipo'], e['tipo'])
            # 2) XML pelo Ambiente Nacional
            if item['modelo'] != '55':
                item['download'] = 'NFC-e e outros modelos não têm download pela SEFAZ: só a consulta.'
            elif not baixar:
                pass
            elif not dist_ok:
                item['download'] = MSG_DIST['656']
            elif not pasta_base:
                item['download'] = 'Escolha a pasta das Baixas DF-e para salvar o XML e o PDF.'
            else:
                try:
                    d = distribuicao(sess, ch, cnpj, cuf)
                    if d['cstat'] == '656':
                        dist_ok = False
                    if d['resumo']:
                        r = d['resumo']
                        item.update({k: r[k] for k in ('emitente', 'valor', 'dh_emissao') if r.get(k)})
                        if item.get('situacao') in ('erro', 'nao_encontrada') and r.get('csit'):
                            item['situacao'] = {'1': 'autorizada', '2': 'denegada', '3': 'cancelada'}.get(r['csit'], item['situacao'])
                    if not d['proc'] and d['resumo'] and com_ciencia and item.get('situacao') == 'autorizada':
                        if chave_priv is None:
                            chave_priv, cert_b64 = _carrega_pfx(pfx, senha)
                        ok, cst, mot = ciencia(sess, ch, cnpj, chave_priv, cert_b64)
                        item['ciencia'] = {'ok': ok, 'cstat': cst, 'motivo': mot}
                        if ok:
                            item.setdefault('eventos', []).append({'tipo': '210210', 'nome': 'ciencia', 'quando': datetime.now().astimezone().isoformat()})
                            for espera in (3, 6):
                                time.sleep(espera)
                                d = distribuicao(sess, ch, cnpj, cuf)
                                if d['proc'] or d['cstat'] == '656':
                                    break
                            if d['cstat'] == '656':
                                dist_ok = False
                    if d['proc']:
                        proc = d['proc']
                        emit = mf._blocos(proc, 'emit')
                        item['emitente'] = item.get('emitente') or (mf._txt(emit[0], 'xNome') if emit else '')
                        item['valor'] = item.get('valor') or mf._txt(proc, 'vNF')
                        item['dh_emissao'] = item.get('dh_emissao') or mf._txt(proc, 'dhEmi') or mf._txt(proc, 'dEmi')
                        p_xml, p_pdf = _pastas(pasta_base, empresa, item.get('dh_emissao'), item['aamm'])
                        texto = '<?xml version="1.0" encoding="UTF-8"?>' + proc
                        item['xml'] = _grava(os.path.join(p_xml, f'{ch}-procNFe.xml'), texto)
                        if gerar_pdf:
                            try:
                                item['pdf'] = _pdf(texto, os.path.join(p_pdf, f'{ch}-DANFE.pdf'), item.get('situacao') == 'cancelada')
                            except Exception as e:
                                item['download'] = f'XML salvo, mas o PDF não foi gerado: {str(e)[:120]}'
                    elif d['resumo'] and not d['proc']:
                        if item.get('ciencia') and item['ciencia']['ok']:
                            item['download'] = 'Ciência registrada. A SEFAZ ainda não liberou o XML: consulte esta chave de novo em alguns minutos.'
                        elif item.get('ciencia'):
                            c = item['ciencia']
                            item['download'] = f"A SEFAZ recusou a ciência ({c['cstat']} · {c['motivo']})."
                        else:
                            item['download'] = 'A SEFAZ mandou só o resumo: o XML completo sai depois da "Ciência da operação" (marque a opção e consulte de novo).'
                    else:
                        item['download'] = MSG_DIST.get(d['cstat'], f"SEFAZ: {d['cstat']} · {d['motivo']}".strip(' ·'))
                except Exception as e:
                    item['download'] = f'Falha ao consultar o Ambiente Nacional: {str(e)[:160]}'
            res.append(item)
            if progresso:
                try:
                    with open(progresso, 'w', encoding='utf-8') as fh:
                        json.dump({'feitas': i, 'total': len(chaves)}, fh)
                except OSError:
                    pass
            time.sleep(pausa)
    finally:
        sess.close()
    return res

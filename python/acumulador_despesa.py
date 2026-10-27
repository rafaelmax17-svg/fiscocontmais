# -*- coding: utf-8 -*-
"""Corretor do SPED Fiscal · reclassificar o acumulador genérico de despesas (COD_NAT 7000 "DESPESAS").

Cada item do C170 lançado no 7000 recebe a SUGESTÃO do acumulador de despesa certo (7001–7040, lista de acumuladores do
escritório no Domínio), pela descrição do produto (0200) e pelo NCM, com o grau de confiança:
  alta = descrição e NCM apontam o mesmo acumulador · média = só um dos dois decidiu.
Nada é trocado sozinho: o Admin revisa na tela (pode trocar qualquer sugestão) e só os itens marcados são aplicados.
Ao aplicar: troca o COD_NAT do C170 e cadastra no 0400 os acumuladores que ainda não existem no arquivo.
"""
import json
import os
import re
import unicodedata


ACUM = {
    '7001': 'DESP. COM VEICULOS', '7002': 'DESP. COM REPAROS EM ALVENARIA', '7003': 'DESP. COM CESTA BASICA',
    '7004': 'DESP. COM CERTIFICADO DIGITAL', '7005': 'DESP. COM MATERIAL DE ESCRITORIO', '7006': 'DESP. COM LIMPEZA E CONSERVAÇÃO',
    '7007': 'DESP. COM MATERIAL DE EPI', '7008': 'DESP. COM UTENSILIOS', '7009': 'DESP. COM COPA E COZINHA', '7010': 'DESP. COM ALIMENTAÇÃO',
    '7011': 'DESP. COM MANUT EM MAQUINAS/EQUIPAMENTOS', '7012': 'DESP. COM MANUTENÇÕES EM GERAL', '7013': 'DESP. COM BENS DURAVEIS DE PEQ VALOR',
    '7014': 'DESP. COM FERRAMENTAS', '7015': 'DESP. COM ENERGIA ELETRICA', '7016': 'DESP. COM COMBUSTIVEL OU LUBRIFICANTE',
    '7017': 'DESP. COM EMBALAGENS', '7018': 'DESP. COM UNIFORMES', '7019': 'DESP. COM MATERIAL PROMOCIONAL', '7020': 'DESP. COM REPRESENTAÇÃO COMERCIAL',
    '7021': 'DESP. COM GÁS PARA EMPILHADEIRA', '7022': 'DESP. COM CATALOGOS', '7023': 'DESP. COM INTERNET E TELEFONIA',
    '7024': 'DESP. COM CURSOS E TREINAMENTOS', '7025': 'DESP. COM SOFTWARE E SERVIÇOS DIGITAIS', '7026': 'BONIFICAÇÕES/DESPESAS', '7027': 'FRETE/DESPESAS',
    '7028': 'DESP. COM ENTREGA FUTURA (MÃE)', '7029': 'DESP. ENTREGA FUTURA (FILHA)', '7030': 'DESP. COM COMUNICAÇÃO E TELECOMUNICAÇÃO',
    '7031': 'DESP. COM MONITORAMENTO E SEGURANÇA', '7032': 'DESP. COM EQUIPAMENTOS P/ POSTOS DE COMB', '7033': 'DESP. COM PALETES E EXPOSITORES',
    '7034': 'DESP. COM CONFRATERNIZAÇÕES', '7035': 'DESP. NA PRESTAÇÃO DE SERVIÇOS', '7036': 'DESP. NA PREPARAÇÃO DE REFEIÇÕES',
    '7037': 'DESP. NA PROMOÇÃO DE VENDAS E EVENTOS', '7038': 'DESP. HOSPITALARES/LABORATORIAS', '7039': 'DESP. COM HOSPEDAGEM E VIAGEM',
    '7040': 'COMPRA ENTREGA FUTURA (MÃE) - DESPESAS',
}


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s or '').upper())
    return ''.join(ch for ch in s if not unicodedata.combining(ch))


# (regex na descrição, acumulador, motivo) — do mais específico para o mais geral
PALAVRAS = [
    (r'\bPNEU|\bCAMARA DE AR|\bPROTETOR (DE )?CAMARA', '7001', 'pneu / câmara'),
    (r'\bTACOGR', '7001', 'disco do tacógrafo'),
    (r'\bARLA\b', '7016', 'ARLA 32 (aditivo do diesel)'),
    (r'^(?!.*\b(TORNEIRA|PURIFICADOR DE AGUA|CAFE|BEBEDOURO)\b).*(\bFILTRO\b|\bPURIFICADOR DE AR\b|\bELEMENTO FILTRANTE|^VOX |^TURBO T[A-Z]*\d)', '7001', 'filtro de veículo'),
    (r'\bGRAXA\b|\bOLEO\b.*\b(\d+W\d+|SAE|ATF|HIDRAUL|MOTOR|TRANSM|CAMBIO|DIFERENC)|\bLUB(RIF)?\b|\bRIMULA\b|\bURSA\b|\bHAVOLINE\b|\bLUBRAX\b', '7016', 'óleo lubrificante / graxa'),
    (r'\bFLUIDO DE? FREIO|\bANTICONGEL|\bADITIVO (DE )?RADIADOR|\bAGUA DESMINERALIZADA', '7001', 'fluido / aditivo de veículo'),
    (r'\bPASTILHA\b|\bLONA (DE )?FREIO|\bDISCO DE FREIO|\bAMORT|\bROLAMENTO\b.*\b(RODA|CUBO)|\bCUBO\b|\bSAPATA\b|\bQUINTA RODA\b|\bCARRETA\b|\bSCANIA\b|\bMERCEDES|\bMB ?\d{3,4}\b|\bVOLVO\b|\bIVECO\b|\bTOYOTA\b|\bSTRADA\b|\bPALIO\b|\bCOROLLA\b|\bUNO\b|\bRANGER\b|\bF250|\bVW \d|\bFIAT\b|\bS-10|\bFRONTIER\b|\bBANDEIRANTE\b|\bFUSCA\b|\bCARGO\b|\bRANDON\b|\bJOST\b|\bCAPU\b|\bPARACHOQUE|\bPARA-?BRISA|\bPB SCANIA|\bSINALEIRA\b|\bFAROL\b|\bLANT(ERNA)? TRAS|\bRETROVISOR|\bPALHETA\b|\bESCAP(AMENTO)?\b|\bSILENCIOSO\b|\bRADIADOR\b|\bINTERCOOLER\b|\bALTERNADOR\b|\bMOTOR DE ARRANQUE|\bEMBREAGEM\b|\bCARTER\b|\bTERMOSTATIC|\bJUNTA TAMPA|\bCOXIM\b|\bGRAMPO MOLA|\bMOLA (DA |AUX|GAVIAO)|\bVALVULA P ?PNEU|\bBICO DE ENCHER PNEU|\bPE APOIO|\bFAIXA (REFLETIVA|PARACHOQUE)', '7001', 'peça / acessório de veículo'),
    (r'\bBATERIA Z|\bBATERIA \d+ ?AH|\bBATERIA AUTOMOT', '7001', 'bateria de veículo'),
    (r'\bLAMPADA\b.*\b(12V|24V)\b|\bH[1-9] 24V|\bH[1-9] 12V', '7001', 'lâmpada automotiva'),
    (r'\bANTENA MOVEL|\bRADIO PX\b', '7030', 'antena / rádio PX (comunicação)'),
    (r'\bCAFE\b|\bACUCAR\b|\bADOCANTE|\bCHA\b|\bCOADOR\b|\bFILTRO DE PAPEL|\bCOPO DESCART|\bLEITE\b|\bBISCOITO|\bBOLACHA', '7009', 'copa e cozinha'),
    (r'\bARROZ\b|\bFEIJAO\b|\bOLEO (DE )?SOJA|\bMAC(ARRAO)?\b.*\bESPAGUETE|\bESPAGUETE\b|\bFARINHA\b|\bSAL REFINADO|\bEXTRATO (DE )?TOMATE|\bFLOCOS (DE )?MILHO|\bFUBA\b', '7003', 'gênero alimentício de cesta básica'),
    (r'\bLARANJA\b|\bLIMAO\b|\bBANANA\b|\bCARNE\b|\bFRANGO\b|\bREFEICAO|\bMARMITA', '7010', 'alimentação'),
    (r'\bCIMENTO\b|\bTIJ(OLO)?\b|\bAREIA\b|\bPEDRA\b|\bBRITA\b|\bCAL\b|\bARGAMASSA|\bREJUNTE|\bMASSA (ACRILICA|CORRIDA)|\bVERGALH|\bCOL\b.*\bACO\b|\bTELA Q\d|\bARAME RECOZIDO|\bLINHA (\(FIO\) )?P/? ?PEDREIRO|\bVEDACIT|\bHYDROLIN|\bIMPERMEAB|\bALVENARIT|\bKALFACIL|\bMANTA ASFALT|\bMETALON\b|\bBLOCO DE CONCRETO|\bLAJOTA|\bPISO\b|\bPORCELANATO|\bTELHA\b|\bGALVALUME|\bCHAPA PRETA|\bBARRA CHATA|\bPOLICARBONATO|\bPERFIL H|\bFORRO PVC|\bMATA JUNTA|\bBARRA U\b|\bREGUA ALUM', '7002', 'material de construção / alvenaria'),
    (r'\bLUVA\b(?!.*\b(LISA INOX|EMENDA|SOLD\w*|PVC|CORRER|ROSCA|BUCHA)\b)|\bBOTA\b|\bCAPACETE|\bOCULOS\b|\bPROTETOR AURIC|\bMASCARA\b|\bRESPIRADOR|\bBLOQUEADOR SOLAR|\bPROTETOR SOLAR|\bCINTO PARAQ', '7007', 'EPI'),
    (r'\bJALECO|\bCAMISA\b|\bCAMISETA|\bCALCA\b|\bUNIFORME|\bAVENTAL|\bBONE\b', '7018', 'uniforme'),
    (r'\bDETERGENTE|\bDESINF|\bAGUA SANITARIA|\bSABAO\b|\bSABONETE|\bALCOOL (GEL|70)|\bDESENGRAX|\bINTERMAX|\bINTERCAP|\bLIMPA\b|\bVASSOURA\b(?!.*GRAMA)|\bRODO\b|\bPANO DE CHAO|\bPANO RETALHO|\bESTOPA|\bPAP(EL)? HIG|\bPAP(EL)? TOALHA|\bSACO (DE |P/ ?)?LIXO|\bLIXEIRA|\bESPONJA|\bAMACIANTE|\bCERA\b', '7006', 'limpeza e conservação'),
    (r'\bPAPEL SULFITE|\bA4\b|\bCANETA|\bLAPIS\b|\bCLIPS?\b|\bGRAMPO GRAMPEADOR|\bGRAMPEADOR|\bBLOCO RECIBO|\bENVELOPE|\bPASTA\b|\bETIQUETA|\bTONER|\bCARTUCHO|\bPILHA\b|\bFITA (TRANSPARENTE|ADESIVA)', '7005', 'material de escritório'),
    (r'\bTECLADO|\bMOUSE\b|\bHEADSET|\bMONITOR\b|\bIMPRESSORA|\bNOTEBOOK|\bMICROONDAS|\bGELADEIRA|\bBEBEDOURO|\bVENTILADOR|\bFOGAO\b|\bCADEIRA\b|\bARMARIO\b|\bBANQUETA', '7013', 'bem durável de pequeno valor'),
    (r'\bCHAVE (AJUST|COMBIN|GRIFO|DE IMPACTO|FENDA|PHILIPS|ALLEN|BOCA|ESTRELA|CANHAO)|\bJOGO DE CHAVES|\bALICATE|\bMARTELO|\bSERRA\b|\bFORMAO|\bTARRAXA|\bBROCA|\bDISCO (DE )?CORTE|\bDISCO DIAMAN|\bFLAP DISC|\bDISCO FLAP|\bLIXA\b|\bESTILETE|\bLAMINA P/ ?ESTILETE|\bTRENA|\bMULTIMETRO|\bESQUADRO|\bENXADA|\bPA DE BICO|\bMACHADO|\bCAVADEIRA|\bCARRINHO (DE )?MAO|\bCARRINHO P/ ?CARGA|\bMALETA FERRAMENTA|\bCAIXA (DE )?FERRAM|\bGRAMPO TIPO C|\bMACARICO|\bPULVERIZADOR|\bBORRIFADOR|\bEXTENSAO 1/2|\bADAPTADOR IMPACTO|\bELETRODO|\bCUNHA DE MADEIRA|\bCABO P/ ?CAVADEIRA|\bVASSOURA (METAL|PLAST) P/ ?GRAMA|\bREGADOR', '7014', 'ferramenta'),
    (r'\bCAMERA\b|\bDVR\b|\bALARME|\bSENSOR DE PRESENCA|\bCERCA ELETRICA|\bCADEADO|\bFECHADURA', '7031', 'segurança'),
    (r'\bBICO (DE )?ABAST|\bMANGUEIRA (DE )?ABAST|\bBOMBA (DE )?COMBUST|\bPLACA .*(DIESEL|GASOLINA|ETANOL|INFLAMAVEL)|\bCONE SINALIZ|\bFITA ZEBRADA|\bFITA DEMARCACAO|\bCAVALETE|\bBALDE CABO TERRA|\bCALCO DE RODA|\bPORTINHOLA|\bHASTE ATERR|\bGRAMPO ATERRAMENTO', '7032', 'equipamento / sinalização do posto'),
    (r'\bTINTA\b|\bSPRAY COLOR|\bSPRAY FUNDO|\bFUNDO PREPARADOR|\bRESINA ACR|\bTHINNER|\bCORANTE|\bROLO DE LA|\bTRINCHA|\bPINCEL|\bSUPORTE P/ ?ROLO|\bFITA CREPE|\bVEDA ROSCA|\bCOLA\b|\bSILICONE (CINZA|INCOLOR|TRANSP)|\bPU 40|\bADESIVO PLASTICO|\bBORRACHA LIQUIDA|\bDISJUNTOR|\bDPS\b|\bRELE\b|\bTOMADA|\bINTERRUPTOR|\bCABO (FLEXIVEL|P\.?P\.?)|\bFIO\b|\bELETRODUTO|\bQUADRO DE DISTRIB|\bTERMINAL TF|\bLAMPADA LED|\bPAINEL (TECH )?LED|\bREFLETOR LED|\bFITA ISOLANTE|\bAUTO TRANSFORMADOR|\bTORNEIRA|\bREGISTRO\b|\bVALVULA\b|\bJOELHO\b|\bCURVA\b|\bCAP ESGOTO|\bADAPTADOR SOLD|\bLUVA (SOLD|PVC|LISA INOX|EMENDA|CORRER|ROSCA)|\bTE (SOLD|ESGOTO)|\bTUBO\b|\bCANO\b|\bNIPLE|\bCOTOVELO|\bBUCHA DE REDUCAO|\bCONEXAO|\bCONECTOR|\bENGATE RAPIDO|\bASSENTO SANIT|\bVASO\b|\bCUBA\b|\bLAVATORIO|\bPIA\b|\bCHUVEIRO|\bNICHO DE PAREDE|\bANEL DE VEDACAO|\bDOBRADICA|\bPARAFUSO|\bPORCA\b|\bARRUELA|\bARR LISA|\bBARRA ROSQUEADA|\bABRACADEIRA|\bBUCHA\b|\bREBITE|\bCORRENTE\b|\bCHAVE BOIA|\bBOMBA (SUB|ELEVADORA)|\bVIDRO TEMPERADO', '7012', 'manutenção predial (elétrica, hidráulica, pintura, fixação)'),
    (r'\bPRETIN|\bPRETITA|\bKIT BANHO|\bSILICONE SPRAY|\bTOALHA AUTOMOTIVA|\bLUVA MICROFIBRA|\bESPUMA BLOCO|\bADITIVO LONG LIFE|\bPANO XADREZ XCAR|\bAROMATIZ|\bAIR LIFE|\bCARREGADOR VEICULAR', '7001', 'cuidado / acessório de veículo'),
    (r'\bDIFUSOR DE AROMAS|\bODORIZADOR|\bDISPENSER', '7006', 'limpeza e conservação (ambiente)'),
    (r'\bPELUCIA|\bCOLECIONAVE|\bCHAPEU\b|\bCHAVEIRO\b|\bBOLSA XCAR|\bTACO DE BEISEBOL', '7019', 'brinde / material promocional'),
    (r'\bCAIXA TERMICA|\bGARRAF(A|AO) TERMIC', '7008', 'utensílio'),
    (r'\bBARRACA\b', '7013', 'bem durável de pequeno valor'),
    (r'\bFLOR ARTIFICIAL|\bFOLHA DE ORQUIDEA|\bCACHEPO', '7012', 'decoração do ambiente'),
    (r'\bCUSCUZEIRO|\bPANELA|\bTALHER|\bPRATO\b|\bCOPO\b|\bJARRA|\bGARRAFA AIR POT', '7008', 'utensílio'),
    (r'\bSACOLA|\bCAIXA DE PAPELAO|\bFILME STRETCH|\bEMBALAGEM', '7017', 'embalagem'),
    (r'\bPALETE|\bPALLET|\bEXPOSITOR|\bGONDOLA', '7033', 'palete / expositor'),
    (r'\bCERTIFICADO DIGITAL|\bTOKEN\b|\bE-CNPJ|\bE-CPF', '7004', 'certificado digital'),
    (r'\bCURATIVO|\bGAZE\b|\bESPARADRAPO|\bMEDICAMENTO|\bKIT PRIMEIROS', '7038', 'hospitalar / primeiros socorros'),
    (r'\bLONA PLAST|\bLONA PRETA|\bLONA FLEX|\bLONAFIX|\bCINTA P/ ?AMARR|\bCATRACA|\bCORDA\b|\bTAPETE', '7012', 'lona / amarração / acessório geral'),
    (r'\bROLAMENTO\b|\bCORREIA\b|\bPOLIA\b|\bRETENTOR|\bROLDANA', '7011', 'peça de máquina / equipamento'),
    (r'\bMAQUINA DE SOLDA|\bENGATE 13MM P/ ?PAINEL|\bGARRA NEGATIVA|\bDESEMPENADEIRA|\bESPATULA|\bCAIXA DE MASSA', '7014', 'ferramenta'),
    (r'\bMANG(UEIRA)?\b.*\bBOMBA COMB|\bMANG BOMBA COMB', '7032', 'mangueira da bomba de combustível'),
    (r'\bMANGUEIRA (HIDRAULICA|DE SUCCAO|RETORNO)|\bFLEXIVEL\b|\bMACHO GIRATORIO|\bJUNTA DE CALCO|\bJTA TAMPA|\bADITIVO RAD|\bTAMPA EXTERNA CLIMAT|\bCINTA DE TANQUE|\bREFIL BOMBA ELETRICA COMBUSTIVEL|\bARREBITE P/ ?LONA|\bDRENO\b|\bFITA AUTOMOTIVA|\bDESENGRIPANTE', '7001', 'peça / insumo de veículo'),
    (r'\bKIT GAS', '7009', 'kit de gás (cozinha)'),
    (r'\bODORIZADOR', '7006', 'limpeza e conservação'),
    (r'\bABRACAD(EIRA)? NYLON|\bENFORCA GATO|\bPRESILHA|\bCAIXA PLASTICA ORGANIZ|\bPLACA 4X2|\bPASSAR PLA|\bBOTAO P/ ?VIDRO|\bTRAVA ROLETE|\bENGATE FLEX|\bCABO C/ ?ROSCA', '7012', 'manutenção geral'),
    (r'\bFICUS|\bDRACENA|\bARV(ORE)?\.? |\bA\.C\.N\.P|\bPLANTA ARTIFICIAL', '7012', 'decoração do ambiente'),
    (r'\bALLTAK|\bADESIVO VINIL|\bBANNER|\bFAIXA PROMOC', '7019', 'comunicação visual / promocional'),
]

# NCM (início) -> acumulador, quando a descrição não decidiu
NCM = [
    ('4011', '7001'), ('4013', '7001'), ('8708', '7001'), ('8512', '7001'), ('6813', '7001'), ('8409', '7001'), ('8507', '7001'),
    ('3819', '7001'), ('3820', '7001'), ('8421', '7001'), ('7320', '7001'), ('9031', '7001'), ('8716', '7001'),
    ('2710', '7016'), ('3403', '7016'), ('2711', '7016'),
    ('2523', '7002'), ('6904', '7002'), ('6810', '7002'), ('2517', '7002'), ('2505', '7002'), ('3214', '7002'), ('7308', '7002'), ('7314', '7002'),
    ('3917', '7012'), ('8536', '7012'), ('8544', '7012'), ('8481', '7012'), ('7307', '7012'), ('3208', '7012'), ('3209', '7012'), ('3506', '7012'),
    ('8539', '7012'), ('7318', '7012'), ('6910', '7012'), ('3922', '7012'), ('8301', '7031'), ('8302', '7012'), ('3814', '7012'), ('7326', '7012'),
    ('8201', '7014'), ('8202', '7014'), ('8203', '7014'), ('8204', '7014'), ('8205', '7014'), ('8207', '7014'), ('8211', '7014'), ('8467', '7014'),
    ('6804', '7014'), ('6805', '7014'), ('9015', '7014'), ('8311', '7014'),
    ('3402', '7006'), ('3401', '7006'), ('3808', '7006'), ('2828', '7006'), ('4818', '7006'), ('9603', '7006'),
    ('4015', '7007'), ('6116', '7007'), ('9004', '7007'), ('6506', '7007'), ('6401', '7007'), ('6402', '7007'), ('6403', '7007'),
    ('4802', '7005'), ('4820', '7005'), ('9608', '7005'), ('8305', '7005'), ('8472', '7005'), ('8506', '7005'),
    ('8471', '7013'), ('8518', '7013'), ('8516', '7013'), ('8418', '7013'), ('9403', '7013'),
    ('0901', '7009'), ('1701', '7009'), ('1006', '7003'), ('0713', '7003'), ('1507', '7003'), ('1902', '7003'), ('1101', '7003'),
    ('0805', '7010'), ('3004', '7038'), ('3005', '7038'), ('6211', '7018'), ('6203', '7018'), ('6204', '7018'), ('6205', '7018'),
    ('4415', '7033'), ('8482', '7011'), ('4010', '7011'), ('8483', '7011'),
]


def classifica(descr, ncm, cfop=''):
    d, n = _norm(descr), re.sub(r'\D', '', str(ncm or ''))
    cf = str(cfop or '')
    if cf[1:] in ('910', '911'):
        return '7026', f'CFOP {cf}: bonificação/brinde', 'alta'
    if cf[1:] in ('922',):
        return '7028', f'CFOP {cf}: entrega futura (nota mãe)', 'alta'
    if cf[1:] in ('116', '117'):
        return '7029', f'CFOP {cf}: entrega futura (nota filha)', 'alta'
    por_ncm = next((a for p, a in NCM if n.startswith(p)), None)
    for rx, ac, mot in PALAVRAS:
        if re.search(rx, d):
            conf = 'alta' if por_ncm == ac or por_ncm is None else 'media'
            obs = '' if conf == 'alta' else f' (o NCM {ncm} sugere {por_ncm})'
            return ac, f'{mot}{obs}', conf
    if por_ncm:
        return por_ncm, f'pelo NCM {ncm}', 'media'
    return '', 'não deu para identificar pela descrição nem pelo NCM', 'confirmar'


ACUM_GENERICO = '7000'


def _itens_7000(linhas):
    p200, p150 = {}, {}
    for l in linhas:
        c = l.split('|')
        if len(c) > 3 and c[1] == '0200':
            p200[c[2]] = (c[3], c[8] if len(c) > 8 else '')
        elif len(c) > 3 and c[1] == '0150':
            p150[c[2]] = c[3]
    out, cur = [], None
    for i, l in enumerate(linhas):
        c = l.split('|')
        if len(c) < 3:
            continue
        if c[1] == 'C100':
            cur = c
        elif c[1] == 'C170' and len(c) > 12 and c[12] == ACUM_GENERICO and cur:
            d, n = p200.get(c[3], ('', ''))
            try:
                v = float(c[7].replace('.', '').replace(',', '.')) if c[7].count(',') else float(c[7] or 0)
            except ValueError:
                v = 0.0
            out.append({'i': i, 'item': c[3], 'descr': d, 'ncm': n, 'cfop': c[11], 'valor': v,
                        'nota': cur[8] if len(cur) > 8 else '', 'forn': p150.get(cur[4], cur[4]) if len(cur) > 4 else ''})
    return out


def analisar_texto(texto):
    linhas = texto.splitlines()
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    if fim is not None:
        linhas = linhas[:fim + 1]
    itens = _itens_7000(linhas)
    prod = {}
    for it in itens:
        p = prod.setdefault(it['item'], {'item': it['item'], 'descr': it['descr'], 'ncm': it['ncm'], 'linhas': 0, 'valor': 0.0,
                                          'cfops': set(), 'notas': set()})
        p['linhas'] += 1
        p['valor'] += it['valor']
        p['cfops'].add(it['cfop'])
        p['notas'].add(it['nota'])
    lista = []
    for p in prod.values():
        cf = sorted(p['cfops'])
        ac, mot, conf = classifica(p['descr'], p['ncm'], cf[0] if len(cf) == 1 else '')
        lista.append({'item': p['item'], 'descr': p['descr'], 'ncm': p['ncm'], 'linhas': p['linhas'], 'valor': round(p['valor'], 2),
                      'cfops': cf, 'notas': sorted(p['notas'])[:8], 'qtd_notas': len(p['notas']),
                      'sugestao': ac, 'motivo': mot, 'confianca': conf})
    lista.sort(key=lambda x: -x['valor'])
    existentes = {l.split('|')[2] for l in linhas if l.startswith('|0400|')}
    return {'itens': lista, 'acumuladores': [{'cod': k, 'nome': v} for k, v in ACUM.items()],
            'resumo': {'linhas': len(itens), 'produtos': len(lista), 'valor': round(sum(i['valor'] for i in itens), 2)},
            'existentes_0400': sorted(existentes)}


def aplicar_texto(texto, selecao):
    """selecao = {'itens': {COD_ITEM: '7001', ...}} -> (texto_novo, resumo)."""
    from fiscal_core import _recalcula_bloco9_global, _recalcula_fechamentos_bloco
    quebra = '\r\n' if '\r\n' in texto else '\n'
    final_vazio = texto.endswith(quebra)
    linhas = texto.split(quebra)
    if final_vazio:
        linhas.pop()
    # arquivo já assinado no PVA: a assinatura vem depois do |9999| e deixa de valer com qualquer alteração
    fim = next((i for i, l in enumerate(linhas) if l.startswith('|9999|')), None)
    assinado = fim is not None and fim < len(linhas) - 1
    if assinado:
        linhas = linhas[:fim + 1]
        final_vazio = True
    mapa = {str(k): str(v) for k, v in ((selecao or {}).get('itens') or {}).items() if str(v) in ACUM}
    alterados, usados, valor = 0, set(), 0.0
    for it in _itens_7000(linhas):
        novo = mapa.get(it['item'])
        if not novo:
            continue
        c = linhas[it['i']].split('|')
        c[12] = novo
        linhas[it['i']] = '|'.join(c)
        alterados += 1
        usados.add(novo)
        valor += it['valor']
    # o 0400 do 7000 sai se nenhum item usa mais esse código (cadastro sem uso)
    usa_generico = any(l.startswith('|C170|') and len(l.split('|')) > 12 and l.split('|')[12] == ACUM_GENERICO for l in linhas)
    removido_0400 = False
    if not usa_generico:
        n0 = len(linhas)
        linhas = [l for l in linhas if not (l.startswith('|0400|') and l.split('|')[2] == ACUM_GENERICO)]
        removido_0400 = len(linhas) < n0
    existentes = {l.split('|')[2] for l in linhas if l.startswith('|0400|')}
    novos_0400 = [f'|0400|{k}|{_norm(ACUM[k])}|' for k in sorted(usados - existentes)]   # sem acento: o arquivo é ISO-8859-1
    if novos_0400:
        pos = max((i for i, l in enumerate(linhas) if l.startswith('|0400|')), default=None)
        if pos is None:
            pos = max(i for i, l in enumerate(linhas) if l[:6] in ('|0150|', '|0190|', '|0200|', '|0205|', '|0206|', '|0220|'))
        linhas[pos + 1:pos + 1] = novos_0400
    linhas = _recalcula_bloco9_global(linhas)
    linhas = _recalcula_fechamentos_bloco(linhas)
    resumo = {'alterados': alterados, 'valor': round(valor, 2), 'acumuladores': sorted(usados), 'novos_0400': novos_0400,
              'restantes': len(_itens_7000(linhas)), 'removido_0400': removido_0400,
              'avisos': (['O arquivo estava assinado no PVA: a assinatura foi retirada (ela deixa de valer com a alteração). Valide e assine de novo no PVA.']
                         if assinado else [])}
    return quebra.join(linhas) + (quebra if final_vazio else ''), resumo


def main_cli(argv):
    def opt(n):
        return argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else None
    sped, js = opt('--sped'), opt('--json')
    if not sped or not js:
        print('uso: acum-7000 --sped ARQ.txt --json saida.json [--aplicar selecao.json --saida novo.txt]')
        return 1
    try:
        import difal_ro as dr
        texto, enc = dr._ler(sped)
        if opt('--aplicar'):
            with open(opt('--aplicar'), 'r', encoding='utf-8') as fh:
                sel = json.load(fh)
            novo, res = aplicar_texto(texto, sel)
            tmp = opt('--saida') + '.parcial'
            with open(tmp, 'w', encoding=enc, newline='') as fh:
                fh.write(novo)
            os.replace(tmp, opt('--saida'))
        else:
            res = analisar_texto(texto)
    except Exception as e:  # pragma: no cover
        res = {'erro': f'Falha ao processar: {e}'}
    tmp = js + '.parcial'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False)
    os.replace(tmp, js)
    return 0

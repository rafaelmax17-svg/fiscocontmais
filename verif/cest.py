import re, json, urllib.request, urllib.parse, subprocess
fontes = ['https://portal.sefaz.pb.gov.br/attachments/article/1519/' + urllib.parse.quote('ANEXO  05 REL. MERC.EF. SUBST. TRIB. E RESP. TAX. VAL.  AGREG. NR A PARTIR DE 01.01.2024   ATUALIZADO EM 05.02.2025.pdf'),
          'https://portal.sefaz.pb.gov.br/attachments/article/7767/' + urllib.parse.quote('ANEXO 05.pdf')]
out = {}
for n, url in enumerate(fontes):
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=120).read()
        open(f'verif/pb{n}.pdf', 'wb').write(raw)
        subprocess.run(['pdftotext', '-layout', f'verif/pb{n}.pdf', f'verif/pb{n}.txt'], check=True)
        txt = open(f'verif/pb{n}.txt', encoding='utf-8', errors='replace').read()
        codes = sorted(set(re.findall(r'\b(\d\d\.\d{3}\.\d\d)\b', txt)))
        out[url] = codes
        print('RESULTADO', n, len(raw), len(codes), codes[:2], codes[-2:], '17.087.04' in codes, '17.003.01' in codes, '03.025.00' in codes)
    except Exception as e:
        print('RESULTADO', n, 'falhou', e)
json.dump(out, open('verif/cest_oficial.json', 'w'), indent=0)

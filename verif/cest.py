import re, json, urllib.request, html
url = 'https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18'
raw = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=120).read()
try:
    t = raw.decode('utf-8')
except UnicodeDecodeError:
    t = raw.decode('latin1')
open('verif/cv142_18.html', 'w', encoding='utf-8').write(t)
txt = html.unescape(re.sub(r'<[^>]+>', ' ', t))
codes = sorted(set(re.findall(r'\b(\d\d\.\d{3}\.\d\d)\b', txt)))
json.dump({'fonte': url, 'tamanho_html': len(t), 'cest': codes}, open('verif/cest_confaz.json', 'w'), indent=0)
print('RESULTADO', len(t), len(codes), codes[:3], codes[-3:])

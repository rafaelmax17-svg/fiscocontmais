import json, os, time, base64, subprocess
import google.auth, google.auth.transport.requests, requests
cred, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
cred.refresh(google.auth.transport.requests.Request())
H = {'Authorization': f'Bearer {cred.token}', 'x-goog-user-project': 'fiscocontmais', 'Content-Type': 'application/json'}
P = 'fiscocontmais'
log = []
r = requests.post(f'https://serviceusage.googleapis.com/v1/projects/{P}/services/texttospeech.googleapis.com:enable', headers=H)
log.append(f'ativar: {r.status_code} {r.text[:300]}')
for _ in range(30):
    s = requests.get(f'https://serviceusage.googleapis.com/v1/projects/{P}/services/texttospeech.googleapis.com', headers=H).json()
    if s.get('state') == 'ENABLED':
        break
    time.sleep(10)
log.append(f"estado: {s.get('state')}")
time.sleep(30)
v = requests.get('https://texttospeech.googleapis.com/v1/voices?languageCode=pt-BR', headers=H).json()
chirp = [x for x in v.get('voices', []) if 'Chirp3-HD' in x['name']]
log.append('vozes: ' + ', '.join(f"{x['name']}({x['ssmlGender']})" for x in chirp))
pref = ['Leda']
esc = [x for p in pref for x in chirp if x['name'].endswith('-' + p)] or chirp[:6]
T = json.load(open('voz/textos.json', encoding='utf-8'))
os.makedirs('voz/saida', exist_ok=True)
for x in esc:
    nome = x['name'].split('-')[-1]
    for i, t in enumerate(T):
        body = {'input': {'text': t}, 'voice': {'languageCode': 'pt-BR', 'name': x['name']},
                'audioConfig': {'audioEncoding': 'MP3', 'sampleRateHertz': 44100, 'speakingRate': 1.22}}
        for tent in range(4):
            r = requests.post('https://texttospeech.googleapis.com/v1/text:synthesize', headers=H, json=body)
            if r.ok:
                break
            log.append(f'{nome} {i}: {r.status_code} {r.text[:200]}'); time.sleep(15)
        if r.ok:
            open(f"voz/saida/{x['ssmlGender'].lower()}-{nome}_{i}.mp3", 'wb').write(base64.b64decode(r.json()['audioContent']))
open('voz/saida/log.txt', 'w').write('\n'.join(log))
print('\n'.join(log))

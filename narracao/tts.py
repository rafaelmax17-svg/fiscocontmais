# Narração do vídeo de treinamento (temporário): Google Text-to-Speech, voz Chirp3-HD Leda (pt-BR)
import json, os, base64, time
import google.auth, google.auth.transport.requests, requests
cred, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
cred.refresh(google.auth.transport.requests.Request())
H = {'Authorization': f'Bearer {cred.token}', 'x-goog-user-project': 'fiscocontmais', 'Content-Type': 'application/json'}
T = json.load(open('narracao/textos.json', encoding='utf-8'))
os.makedirs('narracao/saida', exist_ok=True)
log = []
for x in T:
    body = {'input': {'text': x['texto']}, 'voice': {'languageCode': 'pt-BR', 'name': 'pt-BR-Chirp3-HD-Leda'},
            'audioConfig': {'audioEncoding': 'OGG_OPUS', 'sampleRateHertz': 48000, 'speakingRate': float(os.environ.get('VEL', '1.15'))}}
    for tent in range(5):
        r = requests.post('https://texttospeech.googleapis.com/v1/text:synthesize', headers=H, json=body)
        if r.ok:
            break
        log.append(f"{x['id']}: {r.status_code} {r.text[:200]}"); time.sleep(10)
    if r.ok:
        open(f"narracao/saida/{x['id']}.ogg", 'wb').write(base64.b64decode(r.json()['audioContent']))
        log.append(f"{x['id']}: ok")
open('narracao/saida/log.txt', 'w').write('\n'.join(log))
print('\n'.join(log))

import json, os, subprocess, sys, wave
T = json.load(open('voz/textos.json', encoding='utf-8'))
os.makedirs('voz/saida', exist_ok=True)
qual = sys.argv[1]
if qual == 'piper':
    for v in ('pt_BR-faber-medium', 'pt_BR-cadu-medium', 'pt_BR-jeff-medium'):
        for i, t in enumerate(T):
            out = f'voz/saida/{v}_{i}.wav'
            subprocess.run(['python', '-m', 'piper', '-m', f'voz/modelos/{v}.onnx', '-f', out, '--length-scale', '1.05'], input=t.encode(), check=True)
else:
    from kokoro import KPipeline
    import soundfile as sf, numpy as np
    p = KPipeline(lang_code='p')
    for v in ('pf_dora', 'pm_alex', 'pm_santa'):
        for i, t in enumerate(T):
            aud = np.concatenate([a for _, _, a in p(t, voice=v, speed=0.98)])
            sf.write(f'voz/saida/kokoro-{v}_{i}.wav', aud, 24000)

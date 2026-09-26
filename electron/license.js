'use strict';
// Bloqueio remoto por máquina ("licença").
//
// IMPORTANTE — por que isso usa o SDK CLIENTE do Firebase (pacote "firebase"),
// e não o "firebase-admin" que a sincronização de nuvem já usa:
// o firebase-admin tem uma credencial de administrador com poder total sobre o
// banco. Se esse arquivo algum dia vazar junto com o sistema, quem pegasse ele
// conseguiria marcar a própria máquina como "ativo" e o bloqueio deixaria de
// valer. O SDK cliente, com autenticação anônima e Regras de Segurança no
// Firestore, só consegue LER o status e CRIAR o próprio registro como
// "pendente" — nunca aprovar a si mesmo. Só o painel Admin (que usa a
// credencial privilegiada, a mesma da nuvem) consegue ativar ou bloquear.

const os = require('os');
const crypto = require('crypto');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');

let firebaseApp = null;
let authMod = null;
let fsMod = null;
let dbClient = null;
let cfg = null;

function _configPath() {
  return path.join(__dirname, 'firebaseWebConfig.json');
}

// Config pública do Firebase (apiKey etc. NÃO é segredo — é feita pra ir
// embutida em apps cliente; a segurança vem das Regras do Firestore, não de
// esconder essa config). Enquanto o arquivo não for preenchido, o recurso
// fica desligado (o app libera normalmente — "modo não configurado").
function _loadConfig() {
  if (cfg !== null) return cfg;
  try {
    const raw = JSON.parse(fs.readFileSync(_configPath(), 'utf-8'));
    cfg = raw && raw.apiKey ? raw : false;
  } catch (_) {
    cfg = false;
  }
  return cfg;
}

function isConfigured() {
  return !!_loadConfig();
}

// --------------------------------------------------------------------- código da máquina
function _regGuidWindows() {
  return new Promise((resolve) => {
    execFile('reg', ['query', 'HKLM\\SOFTWARE\\Microsoft\\Cryptography', '/v', 'MachineGuid'],
      { windowsHide: true }, (err, stdout) => {
        if (err) return resolve('');
        const m = /MachineGuid\s+REG_SZ\s+([0-9a-fA-F-]+)/.exec(stdout || '');
        resolve(m ? m[1].trim() : '');
      });
  });
}

let _cachedCode = null;
async function getMachineCode() {
  if (_cachedCode) return _cachedCode;
  let raw = '';
  if (process.platform === 'win32') raw = await _regGuidWindows();
  if (!raw) raw = os.hostname() + '|' + (os.cpus()[0] || {}).model + '|' + os.homedir();
  const hash = crypto.createHash('sha256').update(raw).digest('hex').toUpperCase();
  // código curto e amigável, tipo "A1B2-C3D4-E5F6"
  const short = hash.slice(0, 12);
  _cachedCode = `${short.slice(0, 4)}-${short.slice(4, 8)}-${short.slice(8, 12)}`;
  return _cachedCode;
}

// --------------------------------------------------------------------- firestore (cliente)
async function _db() {
  if (dbClient) return dbClient;
  const c = _loadConfig();
  if (!c) return null;
  const { initializeApp } = require('firebase/app');
  const { getAuth, signInAnonymously } = require('firebase/auth');
  const { getFirestore } = require('firebase/firestore');
  firebaseApp = initializeApp(c, 'fiscocont-license');
  authMod = getAuth(firebaseApp);
  await signInAnonymously(authMod);
  fsMod = require('firebase/firestore');
  dbClient = getFirestore(firebaseApp);
  return dbClient;
}

function _cachePath(userDataDir) {
  return path.join(userDataDir, 'license-cache.json');
}
function _readCache(userDataDir) {
  try { return JSON.parse(fs.readFileSync(_cachePath(userDataDir), 'utf-8')); }
  catch (_) { return null; }
}
function _writeCache(userDataDir, data) {
  try { fs.writeFileSync(_cachePath(userDataDir), JSON.stringify(data)); } catch (_) {}
}
const OFFLINE_GRACE_DIAS = 7;

// Consulta o status desta máquina. Se ela nunca apareceu antes, cria o
// registro como "pendente" (as Regras do Firestore só deixam criar com esse
// status — nunca "ativo"). Devolve { configurado, codigo, status, hostname }.
// userDataDir habilita um cache local: se a internet cair, usa o último
// status "ativo" confirmado por até 7 dias, em vez de travar o escritório.
async function checkLicense(userDataDir) {
  const codigo = await getMachineCode();
  const c = _loadConfig();
  if (!c) return { configurado: false, codigo, status: 'ativo', hostname: os.hostname() };
  try {
    const db = await _db();
    const { doc, getDoc, setDoc, serverTimestamp } = fsMod;
    const ref = doc(db, 'licencas', codigo);
    const snap = await getDoc(ref);
    let status, hostname = os.hostname();
    if (!snap.exists()) {
      await setDoc(ref, {
        status: 'pendente',
        hostname,
        plataforma: `${process.platform} ${os.release()}`,
        primeiroAcesso: serverTimestamp(),
        ultimoAcesso: serverTimestamp(),
      });
      status = 'pendente';
    } else {
      try { await setDoc(ref, { ultimoAcesso: serverTimestamp() }, { merge: true }); } catch (_) {}
      const d = snap.data();
      status = d.status || 'pendente';
      hostname = d.hostname || hostname;
    }
    if (userDataDir) _writeCache(userDataDir, { codigo, status, ts: Date.now() });
    return { configurado: true, codigo, status, hostname };
  } catch (e) {
    // rede fora do ar / regra bloqueando: usa o cache local (só se era "ativo" e recente)
    if (userDataDir) {
      const cache = _readCache(userDataDir);
      if (cache && cache.codigo === codigo && cache.status === 'ativo') {
        const diasPassados = (Date.now() - cache.ts) / 86400000;
        if (diasPassados <= OFFLINE_GRACE_DIAS) {
          return { configurado: true, codigo, status: 'ativo', hostname: os.hostname(), offlineCache: true };
        }
      }
    }
    return { configurado: true, codigo, status: 'offline', hostname: os.hostname(), erro: String(e.message || e) };
  }
}

// --------------------------------------------------------------------- listener em tempo real
// Em vez de só reconferir de tempos em tempos, escuta o documento da própria
// máquina no Firestore — quando o Admin muda o status (Ativar/Bloquear), o
// app é avisado em segundos, não em até 2h. Continua existindo um polling de
// segurança por trás (ver checkLicenseGate no renderer), pro caso raro do
// listener cair silenciosamente (queda de rede) sem soltar erro.
let _unsubListener = null;
async function startLicenseListener(onChange, onStatus) {
  const codigo = await getMachineCode();
  const c = _loadConfig();
  if (!c) { if (onStatus) onStatus({ ok: false, motivo: 'nao_configurado' }); return () => {}; }
  try {
    const db = await _db(); // garante fsMod carregado
    const { doc, onSnapshot } = fsMod;
    const ref = doc(db, 'licencas', codigo);
    if (_unsubListener) { try { _unsubListener(); } catch (_) {} }
    let recebeuPrimeiro = false;
    _unsubListener = onSnapshot(ref, (snap) => {
      // 1ª leitura que chega confirma round-trip completo (conexão + regra
      // de segurança do Firestore permitindo LER este doc) — é o sinal mais
      // confiável de que o listener está realmente ativo, não só "anexado".
      if (!recebeuPrimeiro) { recebeuPrimeiro = true; if (onStatus) onStatus({ ok: true }); }
      if (!snap.exists()) return;
      const d = snap.data();
      onChange({ configurado: true, codigo, status: d.status || 'pendente', hostname: d.hostname || os.hostname() });
    }, (err) => {
      // listener caiu DEPOIS de ter conectado (queda de rede, regra mudou,
      // etc.) — antes isso desaparecia sem deixar rastro nenhum; agora avisa
      // o renderer, que mostra isso no painel de Licenças.
      if (onStatus) onStatus({ ok: false, motivo: 'caiu', erro: String((err && err.message) || err) });
    });
    return _unsubListener;
  } catch (e) {
    if (onStatus) onStatus({ ok: false, motivo: 'erro_inicial', erro: String((e && e.message) || e) });
    return () => {};
  }
}

module.exports = { isConfigured, getMachineCode, checkLicense, startLicenseListener };

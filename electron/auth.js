'use strict';
// Login individual (Firebase Authentication · e-mail e senha) e cadastro de usuários pelo Admin.
//
// Cada pessoa tem o próprio login; o perfil (fiscal / contabil / admin) e a situação (ativo / bloqueado) ficam no
// Firestore em usuarios/{uid}. As Regras de Segurança (arquivo firestore.rules na raiz do projeto) garantem que:
//   • só um Admin ativo cadastra, bloqueia ou muda o perfil de alguém;
//   • a pessoa só lê o próprio cadastro;
//   • o primeiro Admin (ADMIN_INICIAL) se cadastra sozinho uma única vez, e só com o e-mail confirmado.
// Nenhuma senha fica no código. Para funcionar sem internet, depois de cada login online fica guardada na máquina
// uma verificação da senha (scrypt, criptografada com o cofre do Windows via safeStorage), válida por 7 dias.
//
// Sem o plano Blaze não há Cloud Functions: o cadastro de um usuário novo cria a conta numa instância separada do
// Firebase (o Admin continua logado) e manda para a pessoa o e-mail de "definir senha".

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const ADMIN_INICIAL = 'rafael.max17@gmail.com';
const PERFIS = ['fiscal', 'contabil', 'admin'];
const OFFLINE_DIAS = 7;

let _app = null, _auth = null, _db = null, _am = null, _fm = null, _cfg = null;
let _sessao = null;                 // { uid, email, nome, perfil, offline }
let _unsub = null;
let _falhas = 0, _travadoAte = 0;

function _config() {
  if (_cfg !== null) return _cfg;
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(__dirname, 'firebaseWebConfig.json'), 'utf-8'));
    _cfg = raw && raw.apiKey ? raw : false;
  } catch (_) { _cfg = false; }
  return _cfg;
}

function _init() {
  if (_app) return true;
  const c = _config();
  if (!c) return false;
  const { initializeApp, getApps } = require('firebase/app');
  const nome = 'fiscocont-usuario';
  _app = getApps().find((a) => a.name === nome) || initializeApp(c, nome);
  _am = require('firebase/auth');
  _fm = require('firebase/firestore');
  _auth = _am.getAuth(_app);
  _db = _fm.getFirestore(_app);
  return true;
}

function _norm(email) { return String(email || '').trim().toLowerCase(); }

function _msgErro(e) {
  const c = (e && e.code) || '';
  if (c === 'auth/invalid-credential' || c === 'auth/wrong-password' || c === 'auth/user-not-found' || c === 'auth/invalid-email')
    return 'E-mail ou senha incorretos.';
  if (c === 'auth/too-many-requests') return 'Muitas tentativas. Aguarde alguns minutos ou redefina a senha.';
  if (c === 'auth/user-disabled') return 'Usuário desativado.';
  if (c === 'auth/email-already-in-use') return 'Esse e-mail já tem conta.';
  if (c === 'auth/weak-password') return 'A senha precisa ter pelo menos 6 caracteres.';
  if (c === 'permission-denied' || /PERMISSION_DENIED|insufficient permissions/i.test(String(e && e.message)))
    return 'O Firebase recusou o acesso. Confira se as Regras de Segurança novas (firestore.rules) foram publicadas.';
  return String((e && e.message) || e);
}
const _offlineErr = (e) => ((e && e.code) || '') === 'auth/network-request-failed' || /network|ENOTFOUND|ECONN|offline/i.test(String(e && e.message));

// ------------------------------------------------------------------ verificação offline (cofre do Windows)
let _safe = null;
function _safeStorage() {
  if (_safe !== null) return _safe;
  try { const { safeStorage } = require('electron'); _safe = safeStorage.isEncryptionAvailable() ? safeStorage : false; }
  catch (_) { _safe = false; }
  return _safe;
}
function _arqOffline(userDataDir) { return path.join(userDataDir, 'sessoes.dat'); }
function _lerOffline(userDataDir) {
  const s = _safeStorage();
  if (!s) return {};
  try { return JSON.parse(s.decryptString(fs.readFileSync(_arqOffline(userDataDir)))); } catch (_) { return {}; }
}
function _gravarOffline(userDataDir, dados) {
  const s = _safeStorage();
  if (!s) return;
  try { fs.writeFileSync(_arqOffline(userDataDir), s.encryptString(JSON.stringify(dados))); } catch (_) {}
}
function _hash(senha, sal) { return crypto.scryptSync(String(senha), Buffer.from(sal, 'hex'), 32, { N: 16384, r: 8, p: 1 }).toString('hex'); }
function _guardaOffline(userDataDir, email, senha, s) {
  const tudo = _lerOffline(userDataDir);
  const sal = crypto.randomBytes(16).toString('hex');
  tudo[email] = { sal, hash: _hash(senha, sal), uid: s.uid, nome: s.nome, perfil: s.perfil, ts: Date.now() };
  _gravarOffline(userDataDir, tudo);
}
function _confereOffline(userDataDir, email, senha) {
  const r = _lerOffline(userDataDir)[email];
  if (!r) return null;
  if ((Date.now() - r.ts) / 86400000 > OFFLINE_DIAS) return null;
  const h = Buffer.from(_hash(senha, r.sal), 'hex');
  if (!crypto.timingSafeEqual(h, Buffer.from(r.hash, 'hex'))) return null;
  return { uid: r.uid, email, nome: r.nome, perfil: r.perfil, offline: true };
}
function _esqueceOffline(userDataDir, email) {
  const tudo = _lerOffline(userDataDir);
  if (tudo[email]) { delete tudo[email]; _gravarOffline(userDataDir, tudo); }
}

// ------------------------------------------------------------------ login
async function _cadastroDoUsuario(u) {
  const { doc, getDoc, setDoc, serverTimestamp } = _fm;
  const ref = doc(_db, 'usuarios', u.uid);
  let snap = await getDoc(ref);
  if (snap.exists()) return snap.data();
  const email = _norm(u.email);
  // convite feito pelo Admin (cadastro de usuário novo)
  const conv = await getDoc(doc(_db, 'convites', email)).catch(() => null);
  if (conv && conv.exists()) {
    const c = conv.data();
    await setDoc(ref, { nome: c.nome || email, email, perfil: c.perfil, ativo: true, criadoEm: serverTimestamp(), criadoPor: c.criadoPor || '' });
    snap = await getDoc(ref);
    return snap.data();
  }
  // primeiro Admin do sistema
  if (email === ADMIN_INICIAL) {
    if (!u.emailVerified) {
      try { await _am.sendEmailVerification(u); } catch (_) {}
      throw Object.assign(new Error('Confirme o seu e-mail: enviamos um link para ' + email + '. Depois de clicar nele, entre de novo.'), { code: 'fc/verificar' });
    }
    await setDoc(ref, { nome: 'Rafael', email, perfil: 'admin', ativo: true, criadoEm: serverTimestamp(), criadoPor: 'inicial' });
    snap = await getDoc(ref);
    return snap.data();
  }
  return null;
}

async function login(userDataDir, email, senha, onBloqueado) {
  email = _norm(email);
  if (!email || !senha) return { ok: false, erro: 'Informe o e-mail e a senha.' };
  if (Date.now() < _travadoAte) {
    return { ok: false, erro: `Muitas tentativas erradas. Tente de novo em ${Math.ceil((_travadoAte - Date.now()) / 1000)} s.` };
  }
  if (!_init()) return { ok: false, erro: 'Configuração do Firebase ausente neste instalador.' };
  try {
    const cred = await _am.signInWithEmailAndPassword(_auth, email, senha);
    const cad = await _cadastroDoUsuario(cred.user);
    if (!cad) { await _am.signOut(_auth); return _falhou('Este e-mail não está cadastrado no FiscoCont+. Peça ao Admin para cadastrar você.'); }
    if (cad.ativo !== true) { await _am.signOut(_auth); _esqueceOffline(userDataDir, email); return _falhou('Usuário bloqueado pelo Admin.'); }
    if (!PERFIS.includes(cad.perfil)) { await _am.signOut(_auth); return _falhou('Perfil do usuário inválido. Peça ao Admin para corrigir.'); }
    _falhas = 0;
    _sessao = { uid: cred.user.uid, email, nome: cad.nome || email, perfil: cad.perfil, offline: false };
    _guardaOffline(userDataDir, email, senha, _sessao);
    _vigia(userDataDir, onBloqueado);
    return { ok: true, ..._sessao };
  } catch (e) {
    if (e && e.code === 'fc/verificar') { try { await _am.signOut(_auth); } catch (_) {} return { ok: false, erro: e.message }; }
    if (_offlineErr(e)) {
      const s = _confereOffline(userDataDir, email, senha);
      if (s) { _falhas = 0; _sessao = s; return { ok: true, ...s, aviso: 'Sem internet: entrou com o último login confirmado (válido por até 7 dias).' }; }
      if (_lerOffline(userDataDir)[email]) return _falhou('Sem internet: e-mail ou senha incorretos.');
      return { ok: false, erro: 'Sem internet e sem login recente salvo neste computador para esse e-mail.' };
    }
    return _falhou(_msgErro(e));
  }
}
function _falhou(msg) {
  _falhas += 1;
  if (_falhas >= 5) _travadoAte = Date.now() + Math.min(15 * 60, 30 * 2 ** (_falhas - 5)) * 1000;
  return { ok: false, erro: msg };
}

// Bloqueio, exclusão ou troca de perfil feitos pelo Admin chegam em segundos.
function _vigia(userDataDir, onBloqueado) {
  if (_unsub) { try { _unsub(); } catch (_) {} _unsub = null; }
  if (!_sessao || _sessao.offline) return;
  const { doc, onSnapshot } = _fm;
  _unsub = onSnapshot(doc(_db, 'usuarios', _sessao.uid), (snap) => {
    if (!_sessao) return;
    const d = snap.exists() ? snap.data() : null;
    if (!d || d.ativo !== true) {
      _esqueceOffline(userDataDir, _sessao.email);
      logout();
      if (onBloqueado) onBloqueado({ motivo: 'bloqueado' });
    } else if (d.perfil !== _sessao.perfil && PERFIS.includes(d.perfil)) {
      _sessao.perfil = d.perfil;
      if (onBloqueado) onBloqueado({ motivo: 'perfil', perfil: d.perfil });
    }
  }, () => {});
}

async function confereSenha(userDataDir, senha) {
  if (!_sessao) return false;
  if (!_sessao.offline && _init() && _auth.currentUser) {
    try {
      const cred = _am.EmailAuthProvider.credential(_sessao.email, senha);
      await _am.reauthenticateWithCredential(_auth.currentUser, cred);
      return true;
    } catch (e) {
      if (!_offlineErr(e)) return false;
    }
  }
  return !!_confereOffline(userDataDir, _sessao.email, senha);
}

function logout() {
  if (_unsub) { try { _unsub(); } catch (_) {} _unsub = null; }
  _sessao = null;
  if (_auth) _am.signOut(_auth).catch(() => {});
}

async function redefinirSenha(email) {
  if (!_init()) return { ok: false, erro: 'Configuração do Firebase ausente.' };
  try { await _am.sendPasswordResetEmail(_auth, _norm(email)); return { ok: true }; }
  catch (e) { return { ok: false, erro: _msgErro(e) }; }
}

// Primeiro acesso do Admin inicial: cria a conta e manda o e-mail de confirmação.
async function criarAdminInicial(email, senha) {
  email = _norm(email);
  if (email !== ADMIN_INICIAL) return { ok: false, erro: 'O primeiro acesso é só para o Admin do sistema. Os demais usuários são cadastrados pelo Admin.' };
  if (!_init()) return { ok: false, erro: 'Configuração do Firebase ausente.' };
  try {
    const cred = await _am.createUserWithEmailAndPassword(_auth, email, senha);
    await _am.sendEmailVerification(cred.user);
    await _am.signOut(_auth);
    return { ok: true, msg: 'Conta criada. Enviamos um link de confirmação para ' + email + '. Clique nele e depois entre com o e-mail e a senha.' };
  } catch (e) { return { ok: false, erro: _msgErro(e) }; }
}

function sessao() { return _sessao ? { ..._sessao } : null; }
function logado() { return !!(_sessao && !_sessao.offline && _auth && _auth.currentUser); }
function db() { return logado() ? _db : null; }
function fsMod() { return _fm; }

// ------------------------------------------------------------------ Admin: usuários
function _exigeAdmin() {
  if (!_sessao || _sessao.perfil !== 'admin') throw new Error('Acesso restrito ao Admin.');
  if (!logado()) throw new Error('Sem internet: o cadastro de usuários precisa de conexão.');
}
const _iso = (v) => (v && typeof v.toDate === 'function' ? v.toDate().toISOString() : null);

async function listarUsuarios() {
  _exigeAdmin();
  const { collection, getDocs } = _fm;
  const out = [];
  (await getDocs(collection(_db, 'usuarios'))).forEach((d) => {
    const v = d.data() || {};
    out.push({ uid: d.id, nome: v.nome || '', email: v.email || '', perfil: v.perfil || '', ativo: v.ativo === true,
               criadoEm: _iso(v.criadoEm), voce: d.id === _sessao.uid });
  });
  const conv = [];
  (await getDocs(collection(_db, 'convites'))).forEach((d) => {
    const v = d.data() || {};
    if (!out.some((u) => u.email === d.id)) conv.push({ email: d.id, nome: v.nome || '', perfil: v.perfil || '', criadoEm: _iso(v.criadoEm) });
  });
  out.sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
  return { usuarios: out, convites: conv };
}

async function cadastrarUsuario({ nome, email, perfil }) {
  _exigeAdmin();
  email = _norm(email);
  nome = String(nome || '').trim();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new Error('E-mail inválido.');
  if (!nome) throw new Error('Informe o nome.');
  if (!PERFIS.includes(perfil)) throw new Error('Perfil inválido.');
  const { doc, setDoc, serverTimestamp } = _fm;
  await setDoc(doc(_db, 'convites', email), { nome, perfil, criadoEm: serverTimestamp(), criadoPor: _sessao.email });
  // cria a conta numa instância separada (o Admin continua logado nesta)
  const { initializeApp, deleteApp } = require('firebase/app');
  const tmp = initializeApp(_config(), 'fc-cadastro-' + Date.now());
  let jaTinha = false;
  try {
    const a2 = _am.getAuth(tmp);
    await _am.createUserWithEmailAndPassword(a2, email, crypto.randomBytes(18).toString('base64url') + 'aA1!');
    await _am.signOut(a2);
  } catch (e) {
    if (((e && e.code) || '') === 'auth/email-already-in-use') jaTinha = true;
    else { await deleteApp(tmp).catch(() => {}); throw new Error(_msgErro(e)); }
  }
  await deleteApp(tmp).catch(() => {});
  await _am.sendPasswordResetEmail(_auth, email);
  return { ok: true, jaTinha, msg: `Enviamos para ${email} o link para definir a senha. No primeiro login a pessoa já entra como ${perfil}.` };
}

async function alterarUsuario(uid, { ativo, perfil, nome }) {
  _exigeAdmin();
  if (uid === _sessao.uid && (ativo === false || (perfil && perfil !== 'admin')))
    throw new Error('Você não pode bloquear nem tirar o perfil Admin de você mesmo.');
  const mud = {};
  if (typeof ativo === 'boolean') mud.ativo = ativo;
  if (perfil) { if (!PERFIS.includes(perfil)) throw new Error('Perfil inválido.'); mud.perfil = perfil; }
  if (nome) mud.nome = String(nome).trim();
  const { doc, updateDoc, serverTimestamp } = _fm;
  await updateDoc(doc(_db, 'usuarios', uid), { ...mud, alteradoEm: serverTimestamp(), alteradoPor: _sessao.email });
  return { ok: true };
}

async function cancelarConvite(email) {
  _exigeAdmin();
  const { doc, deleteDoc } = _fm;
  await deleteDoc(doc(_db, 'convites', _norm(email)));
  return { ok: true };
}

// ------------------------------------------------------------------ Admin: licenças (sem credencial de administrador)
async function listarLicencas() {
  _exigeAdmin();
  const { collection, getDocs } = _fm;
  const itens = [];
  (await getDocs(collection(_db, 'licencas'))).forEach((d) => {
    const v = d.data() || {};
    itens.push({ codigo: d.id, status: v.status || 'pendente', hostname: v.hostname || '', plataforma: v.plataforma || '',
                 versao: v.versao || '', usuario: v.usuario || '',
                 primeiroAcesso: _iso(v.primeiroAcesso), ultimoAcesso: _iso(v.ultimoAcesso) });
  });
  itens.sort((a, b) => new Date(b.ultimoAcesso || 0) - new Date(a.ultimoAcesso || 0));
  return itens;
}
async function statusLicenca(codigo, status) {
  _exigeAdmin();
  if (!['ativo', 'bloqueado', 'pendente'].includes(status)) throw new Error('Status inválido.');
  const { doc, setDoc, serverTimestamp } = _fm;
  await setDoc(doc(_db, 'licencas', codigo), { status, atualizadoPor: _sessao.email, atualizadoEm: serverTimestamp() }, { merge: true });
  return { ok: true };
}

module.exports = {
  ADMIN_INICIAL, login, logout, confereSenha, redefinirSenha, criarAdminInicial, sessao, logado, db, fsMod,
  listarUsuarios, cadastrarUsuario, alterarUsuario, cancelarConvite, listarLicencas, statusLicenca,
};

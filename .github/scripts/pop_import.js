// Importa o POP (EFD ICMS/IPI) para segredos_admin/pop_icms sem que o texto fique legível no repositório.
//   etapa "chave":    gera um par RSA; a chave privada vai para segredos_admin/pop_chave (só Admin); a pública sai no log.
//   etapa "importar": lê .github/pop/pop_icms.enc (AES-256-GCM com a chave AES cifrada em RSA-OAEP pela pública),
//                     abre com a privada do Firestore, grava o texto em segredos_admin/pop_icms e apaga a chave privada.
'use strict';
const fs = require('fs');
const crypto = require('crypto');
const path = require('path');
const req = require('module').createRequire(path.resolve(__dirname, '../../functions/package.json'));
const { initializeApp } = req('firebase-admin/app');
const { getFirestore } = req('firebase-admin/firestore');
initializeApp({ projectId: 'fiscocontmais' });
const db = getFirestore();
(async () => {
  const etapa = process.argv[2];
  if (etapa === 'chave') {
    const { publicKey, privateKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 3072,
      publicKeyEncoding: { type: 'spki', format: 'pem' }, privateKeyEncoding: { type: 'pkcs8', format: 'pem' } });
    await db.doc('segredos_admin/pop_chave').set({ privada: privateKey, em: new Date().toISOString() });
    console.log('CHAVE_PUBLICA_INICIO');
    console.log(Buffer.from(publicKey).toString('base64'));
    console.log('CHAVE_PUBLICA_FIM');
  } else if (etapa === 'importar') {
    const env = JSON.parse(fs.readFileSync('.github/pop/pop_icms.enc', 'utf8'));
    const ch = (await db.doc('segredos_admin/pop_chave').get()).data();
    if (!ch) throw new Error('Chave privada não encontrada (rode a etapa "chave" antes).');
    const aes = crypto.privateDecrypt({ key: ch.privada, padding: crypto.constants.RSA_PKCS1_OAEP_PADDING, oaepHash: 'sha256' }, Buffer.from(env.k, 'base64'));
    const dec = crypto.createDecipheriv('aes-256-gcm', aes, Buffer.from(env.iv, 'base64'));
    dec.setAuthTag(Buffer.from(env.tag, 'base64'));
    const texto = Buffer.concat([dec.update(Buffer.from(env.dados, 'base64')), dec.final()]).toString('utf8');
    await db.doc('segredos_admin/pop_icms').set({ texto, nome: env.nome, paginas: env.paginas, em: new Date().toISOString(), por: 'importado pelo Claude (conversa)' });
    await db.doc('segredos_admin/pop_chave').delete();
    console.log(`POP gravado: ${texto.length} caracteres, ${env.paginas} páginas. Chave privada apagada.`);
  } else throw new Error('etapa inválida');
})().catch((e) => { console.error(e); process.exit(1); });

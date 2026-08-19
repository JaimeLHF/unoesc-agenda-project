/*
 * Service worker da Agenda UNOESC.
 *
 * Escrito à mão, sem plugin de build: a única coisa que ele precisa fazer é
 * guardar a casca do app (HTML, JS, CSS, ícones) para o app abrir rápido no 4G
 * e ser instalável na tela inicial. Uma biblioteca de PWA traria estratégias de
 * cache que este app não pode usar.
 *
 * A REGRA QUE NÃO PODE SER QUEBRADA: nada de `/api` entra em cache. A agenda
 * espera o Moodle responder de propósito — meia agenda velha, numa tela de
 * prazos, é pior que nenhuma, porque o aluno não tem como saber qual metade
 * está velha. Quem decide mostrar dado antigo é o backend, que avisa na tela.
 * Um service worker servindo JSON guardado desfaria isso em silêncio.
 */

// Muda a cada deploy que precise descartar a casca antiga. Os arquivos do Vite
// já vêm com hash no nome, então na prática só o index.html depende disto.
const VERSAO = 'agenda-v2';

// Só o que existe em disco desde o primeiro carregamento. O resto entra sozinho
// conforme o app pede — os bundles têm hash no nome e mudam a cada build.
const CASCA = ['/', '/index.html', '/favicon.svg', '/icone-192.png', '/icone-512.png'];

self.addEventListener('install', (evento) => {
  // `skipWaiting` para a versão nova assumir no próximo carregamento em vez de
  // esperar todas as abas fecharem — em celular a aba fica aberta por semanas.
  evento.waitUntil(
    caches
      .open(VERSAO)
      .then((cache) => cache.addAll(CASCA))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((chaves) =>
        Promise.all(chaves.filter((c) => c !== VERSAO).map((c) => caches.delete(c))),
      )
      .then(() => self.clients.claim()),
  );
});

/** Endereços que o service worker nunca toca. */
function passaDireto(url) {
  return (
    url.pathname.startsWith('/api/') ||
    // O `.ics` é buscado pelo servidor do Google, mas o aluno também abre esse
    // link; servir uma cópia guardada entregaria uma agenda desatualizada.
    url.pathname.startsWith('/calendario/')
  );
}

self.addEventListener('fetch', (evento) => {
  const req = evento.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin || passaDireto(url)) return;

  // Navegação (abrir o app, F5, link direto): rede primeiro. Sem isso, um
  // deploy novo só apareceria depois que o cache expirasse. Sem rede, entrega
  // a casca guardada — o app monta e mostra o próprio aviso de erro, que é
  // melhor que a tela de dinossauro do navegador.
  if (req.mode === 'navigate') {
    evento.respondWith(
      fetch(req)
        .then((resp) => {
          const copia = resp.clone();
          caches.open(VERSAO).then((cache) => cache.put('/index.html', copia));
          return resp;
        })
        .catch(() => caches.match('/index.html')),
    );
    return;
  }

  // Bundle, CSS e ícone: cache primeiro. O nome carrega o hash do conteúdo, e
  // arquivo com hash nunca muda — quando muda, muda o nome.
  evento.respondWith(
    caches.match(req).then((guardado) => {
      if (guardado) return guardado;
      return fetch(req).then((resp) => {
        if (resp.ok && resp.type === 'basic') {
          const copia = resp.clone();
          caches.open(VERSAO).then((cache) => cache.put(req, copia));
        }
        return resp;
      });
    }),
  );
});

/*
 * Notificação push.
 *
 * O conteúdo chega cifrado do servidor e é decifrado aqui pelo navegador —
 * quem roteia (Google no Android, Apple no iPhone) encaminha sem conseguir
 * ler. O `tag` faz o aviso novo substituir o anterior do mesmo tipo em vez de
 * empilhar: o resumo de hoje ocupa o lugar do de ontem, que ninguém vai ler.
 */
self.addEventListener('push', (evento) => {
  let dados = {};
  try {
    dados = evento.data ? evento.data.json() : {};
  } catch {
    /* payload estranho: mostra o genérico em vez de engolir o aviso */
  }

  const titulo = dados.titulo || 'Agenda UNOESC';
  evento.waitUntil(
    self.registration.showNotification(titulo, {
      body: dados.corpo || '',
      icon: '/icone-192.png',
      badge: '/icone-192.png',
      tag: dados.tag || 'agenda',
      data: { url: dados.url || '/' },
    }),
  );
});

/*
 * Toque na notificação: traz para a frente a aba que já está aberta, em vez de
 * abrir mais uma. Quem toca no aviso quer olhar a agenda, não colecionar abas.
 */
self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  const destino = (evento.notification.data && evento.notification.data.url) || '/';

  evento.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((abas) => {
      for (const aba of abas) {
        if (new URL(aba.url).origin === self.location.origin && 'focus' in aba) {
          aba.navigate(destino);
          return aba.focus();
        }
      }
      return self.clients.openWindow(destino);
    }),
  );
});

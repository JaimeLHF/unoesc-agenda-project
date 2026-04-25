/**
 * Integração com Google Identity Services (GIS) para obter um access token
 * OAuth2 com escopo do Google Calendar (events).
 *
 * O Client ID é injetado em build/dev pelo Vite via env VITE_GOOGLE_CLIENT_ID.
 */

const SCOPE = 'https://www.googleapis.com/auth/calendar.events';

/** Tipos mínimos para a parte do GIS que usamos. */
interface TokenResponse {
  access_token?: string;
  error?: string;
  error_description?: string;
}

interface TokenClient {
  callback: (resp: TokenResponse) => void;
  requestAccessToken: (overrides?: { prompt?: string }) => void;
}

interface GoogleAccountsOAuth2 {
  initTokenClient: (config: {
    client_id: string;
    scope: string;
    callback: (resp: TokenResponse) => void;
  }) => TokenClient;
}

declare global {
  interface Window {
    google?: { accounts: { oauth2: GoogleAccountsOAuth2 } };
  }
}

/** Aguarda o script do GIS carregar (até 10s). */
async function waitForGis(): Promise<GoogleAccountsOAuth2> {
  const start = Date.now();
  while (Date.now() - start < 10_000) {
    if (window.google?.accounts?.oauth2) return window.google.accounts.oauth2;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('Google Identity Services não carregou. Verifique sua conexão.');
}

/**
 * Solicita um access token do Google Calendar ao usuário.
 * Abre o popup de consentimento do Google e resolve com o token.
 */
export async function requestGoogleAccessToken(): Promise<string> {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
  if (!clientId) {
    throw new Error(
      'VITE_GOOGLE_CLIENT_ID não configurado. Defina-o em frontend/.env e reinicie o Vite.',
    );
  }

  const oauth2 = await waitForGis();

  return new Promise<string>((resolve, reject) => {
    const tokenClient = oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPE,
      callback: (resp) => {
        if (resp.error || !resp.access_token) {
          reject(new Error(resp.error_description || resp.error || 'Falha na autenticação Google.'));
          return;
        }
        resolve(resp.access_token);
      },
    });
    tokenClient.requestAccessToken({ prompt: 'consent' });
  });
}

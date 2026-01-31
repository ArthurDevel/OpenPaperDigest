import { authClient } from '../services/auth';

function sanitize(str: string, max = 200) {
  return (str || '').replace(/[\r\n]+/g, ' ').replace(/\s{2,}/g, ' ').trim().slice(0, max);
}

export async function sendAddToListMagicLink(email: string, paperTitle?: string) {
  const headers = new Headers();
  headers.set('x-email-template', 'addtolist');
  const title = sanitize(paperTitle || '');
  if (title) headers.set('x-paper-title', title);

  await authClient.signIn.magicLink({
    email,
    callbackURL: '/auth/callback',
    fetchOptions: { headers },
  });
}

export async function sendLoginMagicLink(email: string) {
  await authClient.signIn.magicLink({
    email,
    callbackURL: '/auth/callback',
  });
}


export async function sendRequestPaperMagicLink(email: string, arxivAbsUrl?: string) {
  const headers = new Headers();
  headers.set('x-email-template', 'requestpaper');
  if (arxivAbsUrl) headers.set('x-arxiv-abs-url', arxivAbsUrl);
  await authClient.signIn.magicLink({
    email,
    callbackURL: '/auth/callback',
    fetchOptions: { headers },
  });
}



export type PostLoginAction = {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  url: string;
  body?: unknown;
  redirect?: string;
};

const COOKIE_NAME = 'ps_post_login';
const MAX_AGE_SECONDS = 300;

export function setPostLoginCookie(payload: PostLoginAction) {
  try {
    const val = encodeURIComponent(JSON.stringify(payload));
    document.cookie = `${COOKIE_NAME}=${val}; Max-Age=${MAX_AGE_SECONDS}; Path=/`;
  } catch {}
}

export function readAndClearPostLoginCookie(): PostLoginAction | null {
  try {
    const item = document.cookie
      .split(';')
      .map((s) => s.trim())
      .find((s) => s.startsWith(`${COOKIE_NAME}=`));
    if (!item) return null;
    const raw = decodeURIComponent(item.split('=')[1] || '');
    const parsed = JSON.parse(raw || '{}');
    // clear
    document.cookie = `${COOKIE_NAME}=; Max-Age=0; Path=/`;
    return parsed;
  } catch {
    return null;
  }
}



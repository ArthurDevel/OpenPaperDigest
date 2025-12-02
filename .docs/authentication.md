## Authentication

### Overview

- **BetterAuth (server + client)**: Handles session creation, cookies, and magic-link delivery. We use the BetterAuth client in the browser (`frontend/services/auth.ts`) and a single BetterAuth server instance on the Next.js server (`frontend/authentication/server_auth.ts`).

- **Proxy guard (`frontend/app/api/[...slug]/route.ts`)**: Proxies frontend `/api/*` requests to the Python backend. For protected user routes (e.g., `/api/users/me/list/...`), it verifies the BetterAuth session server-side and injects `X-Auth-Provider-Id` so the backend can trust identity without being directly exposed.

- **Auth handler (`frontend/app/api/auth/[...betterauth]/route.tsx`)**: Mounts BetterAuth’s API (login, magic link verification, etc.). Uses the shared server auth instance.

- **Callback page (`frontend/app/auth/callback/page.tsx`)**: Final redirect destination after magic-link verification. Optionally executes a post-login action (from a cookie) and then redirects.

- **BetterAuth client (`frontend/services/auth.ts`)**: Browser-facing SDK (hooks + actions like `useSession()`, `signIn.magicLink()`, `signOut()`).

- **Shared server auth (`frontend/authentication/server_auth.ts`)**: Central BetterAuth server instance. Used by both the auth handler and the proxy. Centralization is required so the same instance that issues sessions also verifies them.

---

### Practical

#### Send a magic link (via our abstractions)

- Default login email:

```ts
import { sendLoginMagicLink } from '../authentication/magicLink';

await sendLoginMagicLink('user@example.com');
```

- Add-to-list email (uses the add-to-list template and passes the title):

```ts
import { sendAddToListMagicLink } from '../authentication/magicLink';

await sendAddToListMagicLink('user@example.com', paperTitle);
```

#### Select email templates and pass variables

Use our helpers instead of setting headers manually:

- `sendLoginMagicLink(email)` → default login template
- `sendAddToListMagicLink(email, paperTitle)` → add-to-list template with title

#### Post-login cookie (optional)

Store and consume actions using our tiny helpers in `frontend/authentication/postLogin.ts`:

- Set:

```ts
import { setPostLoginCookie } from '../authentication/postLogin';

setPostLoginCookie({
  method: 'POST',
  url: `/api/users/me/list/${paperUuid}`,
  redirect: `/paper/${slug}`,
});
```

- Read and clear in the callback:

```ts
import { readAndClearPostLoginCookie } from '../authentication/postLogin';

const action = readAndClearPostLoginCookie();
if (action) {
  // execute fetch with X-Auth-Provider-Id (proxy injects on protected routes)
  router.replace(action.redirect || '/');
}
```

Cookie TTL defaults to 5 minutes.

#### Protect endpoints

We protect routes in the Next.js proxy (`frontend/app/api/[...slug]/route.ts`) by:

1. Matching protected paths (e.g., `/api/users/me/list/...`).
2. Calling `auth.api.getSession({ headers })` using the shared server auth instance.
3. If session exists, inject `X-Auth-Provider-Id: session.user.id` into the forwarded request; else return 401.

The Python backend is not directly exposed and trusts only the proxy-injected header.

---

### Files and roles

- `frontend/app/api/[...slug]/route.ts`
  - Proxies `/api/*` to the Python backend.
  - Verifies the user session for protected endpoints and injects user identity.

- `frontend/app/api/auth/[...betterauth]/route.tsx`
  - Mounts BetterAuth’s API handler.
  - Uses the shared auth instance.

- `frontend/app/auth/callback/page.tsx`
  - Destination after magic-link verification.
  - Optionally runs a post-login action then redirects.

- `frontend/services/auth.ts`
  - BetterAuth client SDK initialization for React (hooks + actions).

- `frontend/authentication/server_auth.ts`
  - Shared BetterAuth server instance (plugins, hooks, settings).
  - Centralization ensures the same instance issues and verifies sessions.

---

### Flows

#### 1) /login page

1. User enters email on `/login`.
2. Client calls `authClient.signIn.magicLink({ email, callbackURL: '/auth/callback' })`.
3. User receives default “magic link” email.
4. Clicking the link signs the user in and redirects to `/auth/callback`, which redirects to `/`.

#### 2) Add-to-list (not logged in)

1. User clicks “+ Add to list” and enters email inline.
2. Client sets a post-login cookie with `{ method, url, redirect }` and sends a magic link with headers:
   - `x-email-template: addtolist`
   - `x-paper-title: <title>`
3. User receives the “add to list” email template.
4. After verification, `/auth/callback` reads the cookie, verifies session, calls the protected proxy endpoint to add the paper, clears the cookie, and redirects back to the paper page.



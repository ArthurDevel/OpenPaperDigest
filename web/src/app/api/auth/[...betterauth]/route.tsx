import { toNextJsHandler } from "better-auth/next-js";
import { auth } from '../../../../authentication/server_auth';

export const { GET, POST } = toNextJsHandler(auth.handler);

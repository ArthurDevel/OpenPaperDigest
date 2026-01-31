import { betterAuth } from "better-auth";
import { createPool } from 'mysql2/promise';
import { magicLink } from "better-auth/plugins";
import { APIError } from "better-auth/api";
import { Resend } from 'resend';
import { render } from '@react-email/render';
import { MagicLinkEmail } from './emails/magic-link-email';
import { AddToListMagicLinkEmail } from './emails/add-to-list-magic-link-email';
import { RequestPaperMagicLinkEmail } from './emails/request-paper-magic-link-email';
import React from 'react';
import { syncNewUser } from '@/services/users.service';

// Single BetterAuth server instance shared across handlers
if (!process.env.AUTH_MYSQL_URL) {
  throw new Error('AUTH_MYSQL_URL environment variable is not set');
}
const authDbPool = createPool({
  uri: process.env.AUTH_MYSQL_URL,
  waitForConnections: true,
  connectionLimit: 10,
});

export const auth = betterAuth({
  baseURL: process.env.NEXT_PUBLIC_SITE_URL,
  database: authDbPool as any,
  plugins: [
    magicLink({
      sendMagicLink: async ({ email, token, url }, request) => {
        const resend = new Resend(process.env.RESEND_API_KEY);
        try {
          const template = (request?.headers?.get('x-email-template') || '').toLowerCase();
          const isAddToList = template === 'addtolist';
          const isRequestPaper = template === 'requestpaper';
          const paperTitle = request?.headers?.get('x-paper-title') || undefined;
          const arxivAbsUrl = request?.headers?.get('x-arxiv-abs-url') || undefined;

          let subject: string;
          let html: string;

          if (isAddToList) {
            subject = `Sign in to add “${(paperTitle || '').toString()}”`;
            subject = subject.replace(/[\r\n]+/g, ' ').replace(/\s{2,}/g, ' ').trim().slice(0, 200);
            const element = React.createElement(AddToListMagicLinkEmail as any, { magicLink: url, paperTitle });
            html = await render(element);
          } else if (isRequestPaper) {
            subject = 'Confirm your notification for this paper';
            const element = React.createElement(RequestPaperMagicLinkEmail as any, { magicLink: url, arxivAbsUrl });
            html = await render(element);
          } else {
            subject = 'Your Magic Link to Sign In';
            const element = React.createElement(MagicLinkEmail as any, { magicLink: url });
            html = await render(element);
          }

          await resend.emails.send({
            from: 'Open Paper Digest <authentication@notifications.itempasshomelab.org>',
            to: [email],
            subject,
            html,
          });
        } catch (error) {
          throw new APIError("INTERNAL_SERVER_ERROR", {
            message: "Could not send the magic link email. Please try again later.",
          });
        }
      }
    })
  ],
  databaseHooks: {
    user: {
      create: {
        after: async (user) => {
          try {
            await syncNewUser({ id: user.id, email: user.email });
          } catch (error) {
            throw new APIError("INTERNAL_SERVER_ERROR", {
              message: "Failed to sync user to application database.",
            });
          }
        }
      }
    }
  },
  sessionMaxAge: 60 * 60 * 24 * 30,
});



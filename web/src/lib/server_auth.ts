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

// Single BetterAuth server instance shared across handlers
const authDbPool = createPool({
  host: process.env.AUTH_MYSQL_HOST,
  port: Number(process.env.AUTH_MYSQL_PORT),
  user: process.env.AUTH_MYSQL_USER,
  password: process.env.AUTH_MYSQL_PASSWORD,
  database: process.env.AUTH_MYSQL_DATABASE,
  waitForConnections: true,
  connectionLimit: 10,
});

export const auth = betterAuth({
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
          const backendUrl = `http://127.0.0.1:${process.env.NEXT_PUBLIC_CONTAINERPORT_API}/users/sync`;
          try {
            const response = await fetch(backendUrl, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ id: user.id, email: user.email }),
            });
            if (!response.ok) {
              const errorBody = await response.text();
              throw new APIError("INTERNAL_SERVER_ERROR", {
                message: `Sync failed: ${response.status} ${errorBody}`,
              });
            }
          } catch (error) {
            throw new APIError("INTERNAL_SERVER_ERROR", {
              message: "A network error occurred while creating your account. Please try again later.",
            });
          }
        }
      }
    }
  },
  sessionMaxAge: 60 * 60 * 24 * 30,
});



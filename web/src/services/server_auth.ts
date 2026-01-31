import { betterAuth } from "better-auth";
import { magicLink } from "better-auth/plugins";
import { APIError } from "better-auth/api";
import { Resend } from 'resend';
import { render } from '@react-email/render';
import { MagicLinkEmail } from '@/lib/emails/magic-link-email';
import { AddToListMagicLinkEmail } from '@/lib/emails/add-to-list-magic-link-email';
import React from 'react';

// Single BetterAuth server instance shared across handlers
export const auth = betterAuth({
  plugins: [
    magicLink({
      sendMagicLink: async ({ email, token, url }, request) => {
        const resend = new Resend(process.env.RESEND_API_KEY);
        try {
          const isAddToList = (request?.headers?.get('x-email-template') || '').toLowerCase() === 'addtolist';
          const paperTitle = request?.headers?.get('x-paper-title') || undefined;

          let subject: string;
          let html: string;

          if (isAddToList) {
            subject = `Sign in to add “${(paperTitle || '').toString()}”`;
            subject = subject.replace(/[\r\n]+/g, ' ').replace(/\s{2,}/g, ' ').trim().slice(0, 200);
            const element = React.createElement(AddToListMagicLinkEmail as any, { magicLink: url, paperTitle });
            html = await render(element);
          } else {
            subject = 'Your Magic Link to Sign In';
            const element = React.createElement(MagicLinkEmail as any, { magicLink: url });
            html = await render(element);
          }

          await resend.emails.send({
            from: 'Open Paper Digest <login@resend.dev>', // TODO: Replace with your domain
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



import {
  Body,
  Button,
  Container,
  Head,
  Heading,
  Html,
  Img,
  Link,
  Preview,
  Section,
  Text,
} from '@react-email/components';
import * as React from 'react';

interface AddToListMagicLinkEmailProps {
  magicLink?: string;
  paperTitle?: string;
}

const baseUrl = process.env.VERCEL_URL
  ? `https://${process.env.VERCEL_URL}`
  : 'http://localhost:3000';

export const AddToListMagicLinkEmail = ({
  magicLink = 'https://example.com/magic-link',
  paperTitle = 'this paper',
}: AddToListMagicLinkEmailProps) => (
  <Html>
    <Head />
    <Preview>Sign in to add “{paperTitle}” to your list</Preview>
    <Body style={main}>
      <Container style={container}>
        <Img
          src={`${baseUrl}/static/logo.png`}
          width="42"
          height="42"
          alt="Open Paper Digest Logo"
          style={logo}
        />
        <Heading style={heading}>Add to your list</Heading>
        <Text style={paragraph}>
          You requested to add “{paperTitle}” to your list. Click the button
          below to sign in and complete the action.
        </Text>
        <Section style={buttonContainer}>
          <Button style={button} href={magicLink}>
            Sign in and add to list
          </Button>
        </Section>
        <Text style={paragraph}>
          Or copy and paste this URL into your browser:
        </Text>
        <Link href={magicLink} style={link}>
          {magicLink}
        </Link>
      </Container>
    </Body>
  </Html>
);

export default AddToListMagicLinkEmail;

const main = {
  backgroundColor: '#ffffff',
  fontFamily:
    '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen-Sans,Ubuntu,Cantarell,"Helvetica Neue",sans-serif',
};

const container = {
  margin: '0 auto',
  padding: '20px 0 48px',
  width: '580px',
};

const logo = {
  margin: '0 auto',
};

const heading = {
  fontSize: '28px',
  lineHeight: '1.3',
  fontWeight: 700,
  color: '#484848',
  textAlign: 'center' as const,
};

const buttonContainer = {
  padding: '20px 0',
  textAlign: 'center' as const,
};

const button = {
  backgroundColor: '#4f46e5',
  borderRadius: '5px',
  color: '#fff',
  fontSize: '16px',
  fontWeight: 'bold',
  textDecoration: 'none',
  textAlign: 'center' as const,
  display: 'inline-block',
  padding: '12px 20px',
};

const paragraph = {
  fontSize: '14px',
  lineHeight: '22px',
  color: '#484848',
};

const link = {
  color: '#4f46e5',
  wordBreak: 'break-all' as const,
};



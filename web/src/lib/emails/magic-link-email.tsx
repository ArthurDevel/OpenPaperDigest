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
  
  interface MagicLinkEmailProps {
    magicLink?: string;
  }
  
  const baseUrl = process.env.VERCEL_URL
    ? `https://${process.env.VERCEL_URL}`
    : 'http://localhost:3000';
  
  export const MagicLinkEmail = ({
    magicLink = 'https://example.com/magic-link', // Default for preview
  }: MagicLinkEmailProps) => (
    <Html>
      <Head />
      <Preview>Your Magic Link to Sign In to Open Paper Digest</Preview>
      <Body style={main}>
        <Container style={container}>
          <Img
            src={`${baseUrl}/static/logo.png`}
            width="42"
            height="42"
            alt="Open Paper Digest Logo"
            style={logo}
          />
          <Heading style={heading}>Your Magic Link</Heading>
          <Section style={buttonContainer}>
            <Button style={button} href={magicLink}>
              Sign in to Open Paper Digest
            </Button>
          </Section>
          <Text style={paragraph}>
            This link and code will only be valid for the next 5 minutes. If you did
            not request this email, you can safely ignore it.
          </Text>
          <Text style={paragraph}>
            Or, copy and paste this URL into your browser:
          </Text>
          <Link href={magicLink} style={link}>
            {magicLink}
          </Link>
        </Container>
      </Body>
    </Html>
  );
  
  export default MagicLinkEmail;
  
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
    fontSize: '32px',
    lineHeight: '1.3',
    fontWeight: '700',
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
  }

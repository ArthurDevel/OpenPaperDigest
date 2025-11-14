# Analytics Setup

## Files

- [docker-compose.yml](../docker-compose.yml) - Umami and PostgreSQL services configuration
- [frontend/components/UmamiScript.tsx](../frontend/components/UmamiScript.tsx) - Tracking script component that loads Umami analytics
- [frontend/app/layout.tsx](../frontend/app/layout.tsx) - Root layout with Umami script integration
- [.env.example](../.env.example) - Environment variable examples for Umami configuration

## Environment Variables

**Umami Server (Docker):**
- `HOSTPORT_UMAMI` - Port for Umami dashboard (default: 3001)
- `UMAMI_DB_NAME` - PostgreSQL database name (default: umami)
- `UMAMI_DB_USER` - PostgreSQL database user (default: umami)
- `UMAMI_DB_PASSWORD` - PostgreSQL database password (change in production)
- `UMAMI_APP_SECRET` - Secret key for encrypting data (generate random 32-character string)

**Next.js Frontend:**
- `NEXT_PUBLIC_UMAMI_WEBSITE_ID` - Website tracking ID from Umami dashboard (get this after creating website in Umami)

## Quick Start

1. Update `.env` with Umami variables from `.env.example`
2. Start services: `docker-compose up -d umami umami-postgres`
3. Access dashboard at `http://localhost:3001` (login: admin/umami)
4. Create website in dashboard and copy Website ID
5. Add Website ID to `.env` as `NEXT_PUBLIC_UMAMI_WEBSITE_ID`
6. Restart app: `docker-compose restart app`

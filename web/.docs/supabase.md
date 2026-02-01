# Supabase

## Regenerating Database Types

When database schema changes, regenerate TypeScript types:

```bash
cd web
npx supabase gen types typescript --project-id "<PROJECT_REF>" --schema public > src/lib/types/database.types.ts
```

Find `<PROJECT_REF>` in your Supabase dashboard URL: `https://supabase.com/dashboard/project/<PROJECT_REF>`

# Vercel Deployment - Environment Variables

Set these environment variables in your Vercel project settings.

```
NEXT_PUBLIC_SUPABASE_URL=your-supabase-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_CLOUD_RUN_URL=https://your-cloud-run-service.region.run.app
NEXT_PUBLIC_API_TIMEOUT=30000
NODE_ENV=production
```

## Frontend Best Practices

- Use environment groups for staging vs production
- Never commit `.env.local`
- Use `NEXT_PUBLIC_` prefix only for browser-safe values
- Validate environment at build time
- Use incremental static regeneration (ISR) for /cohorts, /subjects pages

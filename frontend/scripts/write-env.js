/**
 * Prebuild script: Writes Vercel environment variables to .env.production.local
 * This allows Vite to read them using its standard import.meta.env mechanism.
 *
 * Vercel provides env vars via process.env, but Vite only reads from .env files.
 * This script bridges that gap.
 */

import { writeFileSync } from 'fs';

const envVars = [];

// Add VITE_API_URL if set in environment
if (process.env.VITE_API_URL) {
  envVars.push(`VITE_API_URL=${process.env.VITE_API_URL}`);
  console.log(`[prebuild] VITE_API_URL=${process.env.VITE_API_URL}`);
}

// Add other VITE_* environment variables if needed
// if (process.env.VITE_OTHER_VAR) {
//   envVars.push(`VITE_OTHER_VAR=${process.env.VITE_OTHER_VAR}`);
// }

if (envVars.length > 0) {
  writeFileSync('.env.production.local', envVars.join('\n') + '\n');
  console.log('[prebuild] Created .env.production.local');
} else {
  console.log('[prebuild] No VITE_* environment variables found, skipping .env.production.local');
}

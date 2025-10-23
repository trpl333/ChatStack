import { drizzle as drizzleNeon } from 'drizzle-orm/neon-http';
import { drizzle as drizzlePostgres } from 'drizzle-orm/postgres-js';
import { neon } from '@neondatabase/serverless';
import postgres from 'postgres';
import * as schema from '@shared/schema';

// Environment-aware database connection
// Development (Replit): Uses Replit PostgreSQL via HTTP
// Production (DigitalOcean): Uses ai-memory PostgreSQL via direct connection
const doDbUrl = process.env.DO_DATABASE_URL;
const replitDbUrl = process.env.DATABASE_URL;
const isProduction = process.env.NODE_ENV === 'production';

let db: ReturnType<typeof drizzleNeon> | ReturnType<typeof drizzlePostgres>;

if (doDbUrl && isProduction) {
  // Production: DigitalOcean ai-memory database
  console.log('🚀 Production mode: Connected to DigitalOcean ai-memory database');
  const client = postgres(doDbUrl);
  db = drizzlePostgres(client, { schema });
} else if (replitDbUrl) {
  // Development: Replit PostgreSQL
  console.log('🔧 Development mode: Connected to Replit PostgreSQL (with Google Sheets backup)');
  const sql = neon(replitDbUrl);
  db = drizzleNeon(sql, { schema });
} else {
  throw new Error('No database URL configured. Set DATABASE_URL (dev) or DO_DATABASE_URL (prod)');
}

export { db };

/* Public runtime config, read from Vite env at build time. None of this is
   secret — it all ships in the bundle. Secrets (GitHub App private key,
   Supabase service role) live only on Render. */

interface Config {
  supabaseUrl: string;
  supabaseAnonKey: string;
  renderApiBase: string;
  githubAppSlug: string;
}

const env = import.meta.env;

export const config: Config = {
  supabaseUrl: env.VITE_SUPABASE_URL ?? '',
  supabaseAnonKey: env.VITE_SUPABASE_ANON_KEY ?? '',
  renderApiBase: env.VITE_RENDER_API_BASE ?? '',
  githubAppSlug: env.VITE_GITHUB_APP_SLUG ?? 'primnox-data',
};

export const isConfigured = (): boolean =>
  !!config.supabaseUrl && !!config.supabaseAnonKey && !!config.renderApiBase;

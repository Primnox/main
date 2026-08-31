/* GitHub App connect flow (CRS/1.0-W §3.5, §8).

   1. `beginInstall()` sends the browser to GitHub's install page for the App,
      with a CSRF `state` stashed in sessionStorage.
   2. GitHub installs the App on ONE repo (the App manifest restricts scope) and
      redirects back to the SPA with `?installation_id=…&state=…`.
   3. `completeInstall()` verifies `state` and POSTs the installation id to
      Render, which mints tokens server-side and records the connection.

   The App private key and every token stay on Render (§3.5). The browser only
   ever holds an installation id. */

const STATE_KEY = 'primnox-web/github-oauth-state';

export interface GitHubConnectDeps {
  appSlug: string;
  renderApiBase: string;
  accessToken: () => Promise<string>;
}

export function beginInstall(appSlug: string): void {
  const state = crypto.randomUUID();
  sessionStorage.setItem(STATE_KEY, state);
  const url = new URL(`https://github.com/apps/${appSlug}/installations/new`);
  url.searchParams.set('state', state);
  window.location.assign(url.toString());
}

export interface InstallCallback {
  installationId: string;
  setupAction: string | null;
}

/** Parse the redirect params, if this page load is a GitHub install callback. */
export function readInstallCallback(search = window.location.search): InstallCallback | null {
  const p = new URLSearchParams(search);
  const installationId = p.get('installation_id');
  if (!installationId) return null;
  const state = p.get('state');
  const expected = sessionStorage.getItem(STATE_KEY);
  sessionStorage.removeItem(STATE_KEY);
  if (!state || state !== expected) {
    throw new Error('GitHub install state mismatch — not completing the connection');
  }
  return { installationId, setupAction: p.get('setup_action') };
}

export async function completeInstall(
  deps: GitHubConnectDeps,
  cb: InstallCallback,
): Promise<{ repoFullName: string }> {
  const res = await fetch(`${deps.renderApiBase}/github/connect`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${await deps.accessToken()}`,
    },
    body: JSON.stringify({ installation_id: cb.installationId }),
  });
  const body = (await res.json().catch(() => ({}))) as { repo_full_name?: string; error?: string };
  if (!res.ok) throw new Error(body.error ?? `connect failed (${res.status})`);
  return { repoFullName: body.repo_full_name ?? '' };
}

export async function githubStatus(
  deps: GitHubConnectDeps,
): Promise<{ status: string; repoFullName: string | null }> {
  const res = await fetch(`${deps.renderApiBase}/github/status`, {
    headers: { authorization: `Bearer ${await deps.accessToken()}` },
  });
  const body = (await res.json().catch(() => ({}))) as {
    status?: string;
    repo_full_name?: string | null;
  };
  return { status: body.status ?? 'disconnected', repoFullName: body.repo_full_name ?? null };
}

export async function disconnectGitHub(deps: GitHubConnectDeps): Promise<void> {
  await fetch(`${deps.renderApiBase}/github/disconnect`, {
    method: 'POST',
    headers: { authorization: `Bearer ${await deps.accessToken()}` },
  });
}

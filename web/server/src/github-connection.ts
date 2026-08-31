/* GitHub App installation → an authed GitHubClient for a user's repo.

   Custody of the App private key lives here (CRS/1.0-W §3.5, §8). The client
   never sees it. `github_connection` stores only the installation id + repo
   metadata; the short-lived installation token is minted per use. */

import { createAppAuth } from '@octokit/auth-app';
import { Octokit } from '@octokit/rest';
import { config } from './config.js';
import { pool } from './db.js';
import { OctokitGitHubClient, type GitHubClient } from './github.js';

export interface ConnectionRow {
  installation_id: string;
  repo_id: string | null;
  repo_full_name: string | null;
  status: string;
}

export async function getConnection(userId: string): Promise<ConnectionRow | null> {
  const { rows } = await pool.query<ConnectionRow>(
    `SELECT installation_id, repo_id, repo_full_name, status
       FROM github_connection WHERE user_id = $1`,
    [userId],
  );
  return rows[0] ?? null;
}

/** Mint an installation token and confirm the single repo the App can see. */
export async function resolveInstallation(installationId: string): Promise<{
  token: string;
  repoFullName: string;
  repoId: number;
}> {
  if (!config.githubAppId || !config.githubAppPrivateKey) {
    throw new Error('GitHub App is not configured on the server');
  }
  const auth = createAppAuth({
    appId: config.githubAppId,
    privateKey: config.githubAppPrivateKey,
  });
  const { token } = await auth({ type: 'installation', installationId: Number(installationId) });

  const kit = new Octokit({ auth: token });
  const { data } = await kit.apps.listReposAccessibleToInstallation({ per_page: 2 });
  const repo = data.repositories[0];
  if (!repo) throw new Error('the installation grants access to no repository');
  return { token, repoFullName: repo.full_name, repoId: repo.id };
}

/** A GitHubClient for the user's connected repo, or null if not connected. */
export async function githubClientFor(userId: string): Promise<GitHubClient | null> {
  const conn = await getConnection(userId);
  if (!conn || conn.status !== 'connected' || !conn.repo_full_name) return null;

  const { token, repoFullName } = await resolveInstallation(conn.installation_id);
  const [owner, repo] = repoFullName.split('/');
  if (!owner || !repo) return null;
  return new OctokitGitHubClient({ token, owner, repo });
}

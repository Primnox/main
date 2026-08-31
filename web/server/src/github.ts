/* GitHub datastore client (CRS/1.0-W §3.5, §W2).

   Batches every file in a sync cycle into ONE commit via the Git Data API
   (blobs → tree → commit → ref). The server only ever writes ciphertext the
   client produced; it never generates repo content of its own beyond the
   cleartext manifest. */

import { Octokit } from '@octokit/rest';

export interface RepoFile {
  path: string;
  /** utf-8 text (sync writes NDJSON of ciphertext rows + the manifest) */
  content: string;
}

export interface GitHubClient {
  readFile(path: string): Promise<string | null>;
  putFiles(files: RepoFile[], message: string): Promise<{ commitSha: string }>;
  repoFullName(): string;
}

export interface OctokitGitHubOptions {
  token: string; // installation token
  owner: string;
  repo: string;
  branch?: string;
  committer?: { name: string; email: string };
}

export class OctokitGitHubClient implements GitHubClient {
  private readonly kit: Octokit;
  private readonly owner: string;
  private readonly repo: string;
  private readonly branch: string;
  private readonly committer: { name: string; email: string };

  constructor(opts: OctokitGitHubOptions) {
    this.kit = new Octokit({ auth: opts.token });
    this.owner = opts.owner;
    this.repo = opts.repo;
    this.branch = opts.branch ?? 'main';
    this.committer = opts.committer ?? { name: 'primnox-sync', email: 'sync@primnox.local' };
  }

  repoFullName(): string {
    return `${this.owner}/${this.repo}`;
  }

  async readFile(path: string): Promise<string | null> {
    try {
      const { data } = await this.kit.repos.getContent({
        owner: this.owner,
        repo: this.repo,
        path,
        ref: this.branch,
      });
      if (!Array.isArray(data) && data.type === 'file' && typeof data.content === 'string') {
        return Buffer.from(data.content, 'base64').toString('utf8');
      }
      return null;
    } catch (e) {
      if ((e as { status?: number }).status === 404) return null;
      throw e;
    }
  }

  async putFiles(files: RepoFile[], message: string): Promise<{ commitSha: string }> {
    const head = await this.getHead();

    const blobs = await Promise.all(
      files.map((f) =>
        this.kit.git.createBlob({
          owner: this.owner,
          repo: this.repo,
          content: Buffer.from(f.content, 'utf8').toString('base64'),
          encoding: 'base64',
        }),
      ),
    );

    const { data: tree } = await this.kit.git.createTree({
      owner: this.owner,
      repo: this.repo,
      ...(head ? { base_tree: head.treeSha } : {}),
      tree: files.map((f, i) => ({
        path: f.path,
        mode: '100644',
        type: 'blob',
        sha: blobs[i]!.data.sha,
      })),
    });

    const { data: commit } = await this.kit.git.createCommit({
      owner: this.owner,
      repo: this.repo,
      message,
      tree: tree.sha,
      parents: head ? [head.commitSha] : [],
      author: { ...this.committer, date: new Date().toISOString() },
      committer: this.committer,
    });

    const ref = `heads/${this.branch}`;
    if (head) {
      await this.kit.git.updateRef({ owner: this.owner, repo: this.repo, ref, sha: commit.sha });
    } else {
      await this.kit.git.createRef({
        owner: this.owner,
        repo: this.repo,
        ref: `refs/${ref}`,
        sha: commit.sha,
      });
    }
    return { commitSha: commit.sha };
  }

  private async getHead(): Promise<{ commitSha: string; treeSha: string } | null> {
    try {
      const { data: ref } = await this.kit.git.getRef({
        owner: this.owner,
        repo: this.repo,
        ref: `heads/${this.branch}`,
      });
      const { data: commit } = await this.kit.git.getCommit({
        owner: this.owner,
        repo: this.repo,
        commit_sha: ref.object.sha,
      });
      return { commitSha: ref.object.sha, treeSha: commit.tree.sha };
    } catch (e) {
      if ((e as { status?: number }).status === 404) return null; // empty repo
      throw e;
    }
  }
}

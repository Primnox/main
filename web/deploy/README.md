# Deploy templates

These live here because they belong in the **`cyanexani/primnox-chat`** repo
(the SPA's own repo, D8), not in `primnox/main`. Copy them to
`.github/workflows/` there once that repo exists.

| File | Purpose |
|---|---|
| `pages.yml` | Build `web/client` and publish `dist/` to GitHub Pages on push to `main`. |
| `ping.yml` | Hit the Render `/health` endpoint every 10 minutes so the free instance never cold-starts during a session (resolves Q5). |

`pages.yml` assumes the client is at the repo root (adjust `working-directory`
if you keep the `web/client` layout). Set the repo's Pages source to
"GitHub Actions".

`ping.yml` needs the repo variable `RENDER_HEALTH_URL` set to
`https://<your-service>.onrender.com/health`.

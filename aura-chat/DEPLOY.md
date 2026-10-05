# Deploying the service

Railway, project `aura-chat`, from `aura-chat/`.

## The one command

```bash
aura-chat/scripts/deploy.sh
```

It deploys from the repo root, waits for the deployment to settle, and then
checks that the build now serving is the one you just pushed. That last step
matters: a dashboard **Redeploy** re-runs the *previous image*, so it reports
success while the old code keeps serving. The script fails loudly on that.

## Why there is no flag any more

`railway up` uploads from the **git repository root**, not the working
directory. This service lives in a subdirectory of the portal's repo, so a
plain `railway up` ships the whole portal — `Core.js`, `App.html`,
`netlify.toml` — and Railpack looks at that, finds no Python, and fails with
*"could not determine how to build the app."*

That used to be handled by remembering `--path-as-root`. It was forgotten
twice, so it is now handled by configuration instead: the service's **Root
Directory is set to `/aura-chat`**, and `railway.json` beside this file pins the
builder and start command.

**Do not pass `--path-as-root` or a path argument.** With Root Directory set,
either one makes Railway look for `aura-chat/aura-chat`.

`rootDirectory` cannot live in `railway.json`, because Railway reads that file
*from* the root directory — it has to be set on the service. It is set; this
note exists so nobody unsets it. To check or restore it:

```bash
railway api 'query($e:String!,$s:String!){serviceInstance(environmentId:$e,serviceId:$s){rootDirectory}}' \
  --var e=<ENVIRONMENT_ID> --var s=<SERVICE_ID>
```

## When a deploy fails with no logs

The build produces nothing useful through `railway logs --build` (two lines,
both "scheduling build"), and `railway status` just says Failed. The real
message is in the dashboard's build log, or through the API:

```bash
railway api 'query($id:String!){ buildLogs(deploymentId:$id, limit:400){ message } }' --var id=<DEPLOYMENT_ID>
```

Zero `deploymentLogs` means the container never started, so the fault is in the
build or the upload — not in the application.

## Python version

`.python-version` pins 3.13. `pyproject.toml` says `requires-python = ">=3.12"`,
which leaves the builder free to pick something older and fail on install.

## Variables

Set once, in Railway, never in the image:

| Variable | Note |
|---|---|
| `TOKEN_SECRET` | **Byte-identical to the portal's Script Property**, or every realtor gets 401 while `/health` stays green |
| `EXEC_URL` | The deployed Apps Script web app |
| `OPENROUTER_API_KEY` | |
| `LLM_MODEL` | |
| `ALLOWED_ORIGINS` | The PWA's origin. Without it the browser blocks the chat before the request leaves the phone, and nothing here records that it happened |
| `ALLOWED_ORIGIN_REGEX` | Netlify draft deploys only. A standing hole in the allowlist — unset it when preview testing ends |

## After deploying

```bash
curl https://<service>/health
curl -H "Authorization: Bearer $TOK" https://<service>/doctor
```

`/doctor` is the real readiness check: it proves the portal accepts our auth
*and* that project data comes back. Then prove the host does not buffer, because
a buffering proxy returns the same 200 as a healthy one:

```bash
curl -N -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"question":"cheapest project"}' https://<service>/chat
```

Events must print one at a time.

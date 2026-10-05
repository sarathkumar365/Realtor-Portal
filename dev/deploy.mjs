/**
 * The only supported way to publish the PWA.
 *
 * `netlify deploy --dir=www` ships whatever happens to be on disk, and www/ is
 * gitignored — so a deploy after a pull, from a stale checkout, or after editing
 * Script.html without rebuilding would publish a bundle derived from source that
 * no longer exists. The service worker is cache-first, so that stale shell then
 * pins itself on every installed phone until the next deploy.
 *
 * Building here, strictly, immediately before handing the directory to Netlify
 * makes that gap impossible to open.
 *
 *   node dev/deploy.mjs           draft deploy (a preview URL, nobody's install)
 *   node dev/deploy.mjs --prod    production
 */
import { spawnSync } from 'node:child_process';
import { build } from './build.mjs';

const prod = process.argv.includes('--prod');

// Strict: no --allow-missing-icons here. A production bundle without icons is not
// installable, which is the entire point of shipping it.
await build();

const args = ['deploy', '--dir=www'];
if (prod) args.push('--prod');
console.log('\n$ netlify ' + args.join(' '));
const r = spawnSync('netlify', args, { stdio: 'inherit' });
process.exit(r.status === null ? 1 : r.status);

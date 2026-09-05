/**
 * The deployed Apps Script web app — the one JSON endpoint both the dev harness
 * and the static PWA build talk to.
 *
 * Override with AK_EXEC=<url> to point a build or the harness at a different
 * deployment (a test deployment, or the harness's own /api during local work).
 *
 * This URL is the app's lifeline: publishing through "New deployment" rather
 * than editing the existing one mints a fresh id and retires the old, and the
 * installed app keeps calling an address that no longer answers. That happened
 * once already -- V1 was replaced by V2 @22 and every phone broke until this
 * line caught up. Always publish by editing the existing deployment; if the id
 * ever does change, change it here and redeploy the bundle.
 */
export const EXEC = process.env.AK_EXEC
  || 'https://script.google.com/macros/s/AKfycbxB20Mc56_q__y-1-EbXGFDVODqwTNv3lyj7zuuuXDm8WVBaCDpHqHWHtIQWXNqDojC-g/exec';

/**
 * The Aura Chat service — a separate deployment from the Apps Script endpoint
 * above, because Apps Script cannot stream and the chat screen is nothing but a
 * stream.
 *
 * Setting this is what turns the chat on. The Apps Script-hosted copy of the
 * portal never gets it: its pages are served from a googleusercontent.com
 * subdomain whose hash varies per deployment, so the service cannot allowlist
 * that origin, and it could not stream to it anyway. Empty here means the
 * "Ask Aura" button never renders and #chat falls back to Home — one flag,
 * rather than a second code path that has to be kept honest.
 *
 * Whatever value ships here must also appear in the service's ALLOWED_ORIGINS,
 * or the browser blocks the POST before it leaves the phone.
 */
export const AURA = process.env.AURA_BASE
  || 'https://aura-chat-production-0711.up.railway.app';

/**
 * The deployed Apps Script web app: the one JSON endpoint the dev harness
 * proxies to for everything but sign-in.
 *
 * Override with AK_EXEC=<url> to point the harness at a different deployment.
 *
 * Publishing through "New deployment" rather than editing the existing one
 * mints a fresh id and retires this address, and the agent's EXEC_URL with it.
 * Always publish by editing the existing deployment.
 */
export const EXEC = process.env.AK_EXEC
  || 'https://script.google.com/macros/s/AKfycbxB20Mc56_q__y-1-EbXGFDVODqwTNv3lyj7zuuuXDm8WVBaCDpHqHWHtIQWXNqDojC-g/exec';

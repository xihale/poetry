#!/usr/bin/env node
/**
 * GitHub push webhook → server-side deploy (no runner involved).
 *
 * systemd socket activation (Accept=yes): every connection spawns this script
 * with the accepted socket as fd 0/1 (inetd-style). We read exactly one HTTP
 * request, verify the GitHub HMAC-SHA256 signature, answer GitHub (it has a
 * ~10s deadline), and only then hand the process over to deploy.sh — so the
 * process exists for seconds unless a deploy is actually running.
 *
 * Server layout (see scripts/server/README.md):
 *   clone:  /home/poetry-ci/poetry
 *   secret: /home/poetry-ci/.webhook-secret (shared with the GitHub hook)
 *   log:    /home/poetry-ci/deploy.log        (deploy.sh output)
 */
import { createHmac, timingSafeEqual } from "node:crypto";
import {
  closeSync,
  existsSync,
  openSync,
  readFileSync,
  readSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT = "poetry";
const SERVER = "gx";
const SECRET_FILE = process.env.POETRY_WEBHOOK_SECRET_FILE ?? "/home/poetry-ci/.webhook-secret";
const DEPLOY_SH = join(HERE, "deploy.sh");
const DEPLOY_LOG = process.env.POETRY_DEPLOY_LOG ?? "/home/poetry-ci/deploy.log";
const HOOK_PATH = process.env.POETRY_HOOK_PATH ?? "/hooks/poetry-deploy";
const STATUS_FILE = process.env.POETRY_STATUS_FILE ?? "/srv/poetry/deploy-status.json";
const NTFY_CONFIG = process.env.POETRY_NTFY_CONFIG ?? "/home/poetry-ci/.ntfy-notify";
const NTFY_URL = process.env.POETRY_NTFY_URL ?? "http://127.0.0.1:8090";
// Only main deploys; the site is the product, there is no staging branch.
const DEPLOY_BRANCHES = new Set(["main"]);
const READ_TIMEOUT_MS = 15_000;

const log = (...a) => console.error(new Date().toISOString(), ...a); // → journald

/** Read method/path/headers/body from the socket on stdin. */
function readRequest() {
  return new Promise((resolve, reject) => {
    let buf = Buffer.alloc(0);
    let headEnd = -1;
    let contentLength = -1;
    let settled = false;
    const finish = (fn) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      process.stdin.removeListener("data", onData);
      process.stdin.removeListener("end", onEnd);
      process.stdin.removeListener("error", onError);
      fn();
    };
    const onData = (chunk) => {
      buf = Buffer.concat([buf, chunk]);
      if (headEnd === -1) {
        headEnd = buf.indexOf("\r\n\r\n");
        if (headEnd === -1) {
          if (buf.length > 64 * 1024) finish(() => reject(new Error("headers too large")));
          return;
        }
        const m = /content-length:\s*(\d+)/i.exec(buf.subarray(0, headEnd).toString("latin1"));
        contentLength = m ? Number(m[1]) : 0;
        if (contentLength > 5 * 1024 * 1024) {
          finish(() => reject(new Error("body too large")));
          return;
        }
      }
      // Stop as soon as the declared body is complete — the client keeps the
      // connection open waiting for our response; reading to EOF would deadlock.
      if (buf.length - (headEnd + 4) >= contentLength) {
        const body = buf.subarray(headEnd + 4, headEnd + 4 + contentLength);
        finish(() => resolve({ head: buf.subarray(0, headEnd).toString("latin1"), body }));
      }
    };
    const onEnd = () => finish(() => reject(new Error("client closed before body complete")));
    const onError = (err) => finish(() => reject(err));
    const timer = setTimeout(() => finish(() => reject(new Error("read timeout"))), READ_TIMEOUT_MS);
    process.stdin.on("data", onData);
    process.stdin.on("end", onEnd);
    process.stdin.on("error", onError);
    process.stdin.resume();
  });
}

/** Write a minimal HTTP response; resolves once flushed to the socket. */
function respond(status, text) {
  const reason = { 200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found" }[status] ?? "Error";
  const body = Buffer.from(text);
  const head =
    `HTTP/1.1 ${status} ${reason}\r\n` +
    `Content-Type: text/plain; charset=utf-8\r\n` +
    `Content-Length: ${body.length}\r\n` +
    `Connection: close\r\n\r\n`;
  return new Promise((resolve) => {
    process.stdout.write(head, () => process.stdout.write(body, resolve));
  });
}

function signatureOk(secret, body, header) {
  if (!header) return false;
  const expected = "sha256=" + createHmac("sha256", secret).update(body).digest("hex");
  const a = Buffer.from(header);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

// Served by Caddy at /deploy-status.json. deploy.sh's rsync excludes this
// name, so the previous result stays readable while a new build runs.
function writeStatus(fields) {
  try {
    writeFileSync(STATUS_FILE, JSON.stringify(fields) + "\n");
  } catch (err) {
    log("status write failed:", err.message);
  }
}

// Push the outcome to the shared ntfy topic `webhook-deploy` (message format
// unified across all webhook-deployed sites: `[project@server] deploy …`).
// NTFY_CONFIG holds the topic on line 1 and a user:pass (write-only ACL on
// the topic) on line 2. Strictly best-effort: a notification outage must
// never fail a deploy.
async function notifyNtfy(status, code, sha, startedAt) {
  try {
    if (!existsSync(NTFY_CONFIG)) return;
    const [topic, userPass] = readFileSync(NTFY_CONFIG, "utf8").trim().split("\n");
    const tookS = Math.max(1, Math.round((Date.now() - Date.parse(startedAt)) / 1000));
    const short = sha.slice(0, 7);
    await fetch(`${NTFY_URL}/${topic}`, {
      method: "POST",
      headers: {
        Authorization: "Basic " + Buffer.from(userPass).toString("base64"),
        Title: `[${PROJECT}@${SERVER}] deploy ${status}`,
        Priority: status === "success" ? "default" : "high",
        Tags: status === "success" ? "white_check_mark" : "rotating_light",
      },
      body:
        status === "success"
          ? `${short} live in ${tookS}s`
          : `${short} failed (exit ${code}): ${failureReason(code)} — ssh ${SERVER}: tail ${DEPLOY_LOG}`,
      signal: AbortSignal.timeout(5000),
    });
  } catch (err) {
    log("ntfy notify failed:", err.message);
  }
}

// The reason a deploy failed: a `FATAL:` line if the run died via die(),
// else the log's final line. Reads only the tail — deploy.log is
// append-only and grows without bound.
function failureReason(code) {
  try {
    const size = statSync(DEPLOY_LOG).size;
    const len = Math.min(size, 8192);
    const buf = Buffer.alloc(len);
    const fd = openSync(DEPLOY_LOG, "r");
    readSync(fd, buf, 0, len, size - len);
    closeSync(fd);
    const lines = buf.toString("utf8").trimEnd().split("\n").reverse();
    return (lines.find((l) => l.includes("FATAL:")) ?? lines[0] ?? "").slice(0, 200) || `exit ${code}`;
  } catch {
    return `exit ${code}`;
  }
}

let req;
try {
  req = await readRequest();
} catch (err) {
  log("read failed:", err.message);
  await respond(400, "bad request\n");
  process.exit(0);
}

const lines = req.head.split("\r\n");
const [method, target = ""] = lines[0].split(" ");
const headers = {};
for (const line of lines.slice(1)) {
  const i = line.indexOf(":");
  if (i > 0) headers[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim();
}

if (method !== "POST" || target.split("?")[0] !== HOOK_PATH) {
  await respond(404, "not found\n");
  process.exit(0);
}

const event = headers["x-github-event"] ?? "";
const secret = readFileSync(SECRET_FILE, "utf8").trim();
if (!signatureOk(secret, req.body, headers["x-hub-signature-256"])) {
  log(`rejected ${event || "(no event)"}: bad signature`);
  await respond(403, "bad signature\n");
  process.exit(0);
}

if (event === "ping") {
  await respond(200, "pong\n");
  process.exit(0);
}
if (event !== "push") {
  await respond(200, `ignored event ${event}\n`);
  process.exit(0);
}

let payload;
try {
  payload = JSON.parse(req.body.toString("utf8"));
} catch {
  await respond(400, "bad json\n");
  process.exit(0);
}

const ref = typeof payload.ref === "string" ? payload.ref : "";
const branch = ref.replace(/^refs\/heads\//, "");
if (payload.deleted || !DEPLOY_BRANCHES.has(branch)) {
  await respond(200, `ignored ${ref}${payload.deleted ? " (deleted)" : ""}\n`);
  process.exit(0);
}

// Answer before building — GitHub's webhook timeout is ~10s.
await respond(200, `deploy started (${ref})\n`);
log(`push ${String(payload.after ?? "").slice(0, 7)} on ${ref} → deploy`);
process.stdin.destroy(); // socket served; deploy.sh owns the process now

const sha = String(payload.after ?? "");
const startedAt = new Date().toISOString();
writeStatus({ status: "building", branch, sha, startedAt });

const logFd = openSync(DEPLOY_LOG, "a");
const child = spawn("/bin/bash", [DEPLOY_SH, ref], {
  stdio: ["ignore", logFd, logFd],
  env: { ...process.env, POETRY_PUSH_SHA: sha },
});
const code = await new Promise((resolve) => child.on("close", resolve));
const status = code === 0 ? "success" : "failure";
writeStatus({
  status,
  branch,
  sha,
  startedAt,
  finishedAt: new Date().toISOString(),
  exitCode: code,
});
await notifyNtfy(status, code, sha, startedAt);
log(`deploy exited ${code}`);
process.exit(code === 0 ? 0 : 1);

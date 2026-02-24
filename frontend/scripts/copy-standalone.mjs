#!/usr/bin/env node
/**
 * Copy public and .next/static into .next/standalone so the standalone server
 * can serve them. Required when using output: 'standalone' in next.config.
 * Run after: npm run build
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const standalone = path.join(root, '.next', 'standalone');

function copyRecursive(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  for (const name of fs.readdirSync(src)) {
    const srcPath = path.join(src, name);
    const destPath = path.join(dest, name);
    if (fs.statSync(srcPath).isDirectory()) {
      copyRecursive(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

if (!fs.existsSync(standalone)) {
  console.warn('[copy-standalone] No .next/standalone found (run npm run build first).');
  process.exit(0);
}

const publicDir = path.join(root, 'public');
const staticDir = path.join(root, '.next', 'static');
const standaloneStatic = path.join(standalone, '.next', 'static');
const standalonePublic = path.join(standalone, 'public');

if (fs.existsSync(publicDir)) {
  copyRecursive(publicDir, standalonePublic);
  console.log('[copy-standalone] Copied public → .next/standalone/public');
}
if (fs.existsSync(staticDir)) {
  copyRecursive(staticDir, standaloneStatic);
  console.log('[copy-standalone] Copied .next/static → .next/standalone/.next/static');
}

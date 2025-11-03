import { access, constants, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');
const e2eRoot = path.resolve(projectRoot, 'tests', 'e2e');
const playwrightConfig = path.resolve(projectRoot, 'playwright.config.ts');

async function collectSpecs(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = await Promise.all(
    entries.map(async entry => {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        return collectSpecs(fullPath);
      }
      if (entry.isFile() && entry.name.endsWith('.e2e.spec.ts')) {
        return [fullPath];
      }
      return [];
    }),
  );
  return files.flat();
}

const specs = await collectSpecs(e2eRoot);

if (specs.length === 0) {
  console.log('No e2e specs found under tests/e2e (*.e2e.spec.ts). Skipping Playwright run.');
  process.exit(0);
}

const args = ['playwright', 'test'];
if (await fileExists(playwrightConfig)) {
  args.push('--config', playwrightConfig);
}

const child = spawn('npx', args, {
  cwd: projectRoot,
  stdio: 'inherit',
  shell: true,
});

child.on('exit', code => {
  process.exit(code ?? 1);
});

async function fileExists(p) {
  try {
    await access(p, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

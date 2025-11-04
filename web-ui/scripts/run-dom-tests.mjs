import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const currentDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(currentDir, '..');

console.log('🧪 Running AgentRouter fallback logic tests...\n');

try {
  // Run simple unit tests for fallback logic
  execSync('npx vitest run tests/unit/agentRouterFallback.test.ts', {
    cwd: projectRoot,
    stdio: 'inherit',
  });

  console.log('\n✅ AgentRouter fallback tests completed successfully!');
} catch (error) {
  console.error('\n❌ AgentRouter fallback tests failed!');
  process.exit(1);
}
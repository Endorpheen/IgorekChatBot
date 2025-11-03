import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const frontendCoverageDir = resolve(currentDir, '../reports/frontend/coverage')

// https://vite.dev/config/
export default defineConfig({
  base: '/web-ui/',
  plugins: [react()],
  test: {
    environment: 'node',
    setupFiles: [],
    include: ['tests/unit/**/*.test.ts', 'tests/unit/**/*.test.tsx'],
    exclude: ['tests/e2e/**'],
    coverage: {
      reportsDirectory: frontendCoverageDir,
      reporter: ['text', 'lcov', 'json'],
      include: ['src/**/*.{ts,tsx}'],
    },
  },
})

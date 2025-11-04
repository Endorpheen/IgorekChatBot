import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'

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
      include: [
        'src/components/CopyButton.tsx',
        'src/components/ImageGenerationPanel.tsx',
        'src/components/SettingsPanel.tsx',
        'src/hooks/useChatState.ts',
        'src/utils/**/*.ts',
      ],
      thresholds: {
        lines: 30,
        functions: 30,
        statements: 30,
        branches: 20,
      },
    },
  },
})

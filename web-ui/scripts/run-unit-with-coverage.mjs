import { access, constants, mkdir, rename, rm } from 'node:fs/promises'
import { createWriteStream } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(projectRoot, '..')
const reportsRoot = path.resolve(repoRoot, 'reports', 'frontend')
const coverageTarget = path.join(reportsRoot, 'coverage')
const logsTarget = path.join(reportsRoot, 'logs')
let logBuffer = ''
await mkdir(reportsRoot, { recursive: true })

const args = [
  'vitest',
  'run',
  '--coverage',
  '--coverage.reporter=text',
  '--coverage.reporter=lcov',
  '--coverage.reporter=json',
  '--coverage.reportsDirectory=../reports/frontend',
]

const child = spawn('npx', args, {
  cwd: projectRoot,
  shell: true,
})

child.stdout.on('data', chunk => {
  process.stdout.write(chunk)
  logBuffer += chunk
})

child.stderr.on('data', chunk => {
  process.stderr.write(chunk)
  logBuffer += chunk
})

const exitCode = await new Promise(resolve => {
  child.on('exit', code => resolve(code ?? 0))
})

if (exitCode === 0) {
  await rm(coverageTarget, { recursive: true, force: true })
  await mkdir(coverageTarget, { recursive: true })

  const coverageFiles = ['coverage-final.json', 'lcov.info']
  for (const filename of coverageFiles) {
    const source = path.join(reportsRoot, filename)
    if (await exists(source)) {
      await rename(source, path.join(coverageTarget, filename))
    }
  }
  const lcovReportSource = path.join(reportsRoot, 'lcov-report')
  if (await exists(lcovReportSource)) {
    await rename(lcovReportSource, path.join(coverageTarget, 'lcov-report'))
  }
}

await mkdir(logsTarget, { recursive: true })
await mkdir(reportsRoot, { recursive: true })
const logFile = path.join(logsTarget, 'unit.log')
const logStream = createWriteStream(logFile, { flags: 'w' })
logStream.write(logBuffer)
logStream.end()

if (exitCode !== 0) {
  process.exitCode = exitCode
}

async function exists(p) {
  try {
    await access(p, constants.F_OK)
    return true
  } catch {
    return false
  }
}

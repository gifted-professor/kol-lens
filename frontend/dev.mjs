import { existsSync } from 'node:fs'
import { spawn, spawnSync } from 'node:child_process'
import process from 'node:process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..')
const devImageReadTimeout = process.env.VISION_IMAGE_READ_TIMEOUT || '10'
const devImageConnectTimeout = process.env.VISION_IMAGE_CONNECT_TIMEOUT || '8'
const devImageDownloadRetries = process.env.VISION_IMAGE_DOWNLOAD_RETRIES || '3'
const devImageDownloadMaxWorkers = process.env.VISION_IMAGE_DOWNLOAD_MAX_WORKERS || '2'

const children = []

function canImportBackendDependencies(pythonPath) {
  if (!existsSync(pythonPath)) return false

  const result = spawnSync(
    pythonPath,
    ['-c', 'import openai, pydantic_core'],
    {
      cwd: repoRoot,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
      },
      stdio: 'ignore',
    },
  )

  return result.status === 0
}

function resolveBackendPython() {
  if (process.env.BACKEND_PYTHON) {
    return process.env.BACKEND_PYTHON
  }

  const candidates = [
    path.join(repoRoot, 'backend', '.venv', 'bin', 'python'),
    path.join(repoRoot, 'backend', 'venv', 'bin', 'python'),
  ]

  for (const candidate of candidates) {
    if (canImportBackendDependencies(candidate)) {
      return candidate
    }
  }

  console.error('[backend] no compatible Python environment found.')
  console.error('[backend] checked:')
  for (const candidate of candidates) {
    console.error(`  - ${candidate}`)
  }
  console.error('[backend] fix by setting BACKEND_PYTHON to a working interpreter or rebuilding the backend venv.')
  process.exit(1)
}

const backendPython = resolveBackendPython()

function startProcess(name, command, args, cwd) {
  const child = spawn(command, args, {
    cwd,
    stdio: 'inherit',
    env: {
      ...process.env,
      FLASK_USE_RELOADER: '0',
      PYTHONUNBUFFERED: '1',
      VISION_IMAGE_READ_TIMEOUT: devImageReadTimeout,
      VISION_IMAGE_CONNECT_TIMEOUT: devImageConnectTimeout,
      VISION_IMAGE_DOWNLOAD_RETRIES: devImageDownloadRetries,
      VISION_IMAGE_DOWNLOAD_MAX_WORKERS: devImageDownloadMaxWorkers,
    },
  })

  child.on('exit', (code, signal) => {
    if (signal) {
      console.log(`[${name}] exited with signal ${signal}`)
    } else if (code && code !== 0) {
      console.log(`[${name}] exited with code ${code}`)
      shutdown(code)
    }
  })

  child.on('error', (error) => {
    console.error(`[${name}] failed to start:`, error.message)
    shutdown(1)
  })

  children.push(child)
  return child
}

function shutdown(exitCode = 0) {
  for (const child of children) {
    if (!child.killed) {
      child.kill('SIGTERM')
    }
  }
  process.exit(exitCode)
}

process.on('SIGINT', () => shutdown(0))
process.on('SIGTERM', () => shutdown(0))

startProcess('backend', backendPython, ['backend/app.py'], repoRoot)
startProcess('frontend', 'npm', ['run', 'dev:frontend', '--', '--host', '127.0.0.1', '--port', '5173'], __dirname)

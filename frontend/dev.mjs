import { spawn } from 'node:child_process'
import process from 'node:process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..')
const backendPython = path.join(repoRoot, 'backend', 'venv', 'bin', 'python')
const archBinary = '/usr/bin/arch'

const children = []

function startProcess(name, command, args, cwd) {
  const child = spawn(command, args, {
    cwd,
    stdio: 'inherit',
    env: {
      ...process.env,
      FLASK_USE_RELOADER: '0',
      PYTHONUNBUFFERED: '1',
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

startProcess('backend', archBinary, ['-x86_64', backendPython, 'backend/app.py'], repoRoot)
startProcess('frontend', 'npm', ['run', 'dev:frontend', '--', '--host', '127.0.0.1', '--port', '5173'], __dirname)

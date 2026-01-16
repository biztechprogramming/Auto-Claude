#!/usr/bin/env node

/**
 * Rebuild Docker Containers Script
 *
 * Cross-platform wrapper to rebuild all Auto-Claude Docker containers.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// Determine platform-specific paths
const isWindows = process.platform === 'win32';
const backendDir = path.join(__dirname, '..', 'apps', 'backend');
const venvPython = isWindows
  ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
  : path.join(backendDir, '.venv', 'bin', 'python');
const rebuildScript = path.join(backendDir, 'rebuild_containers.py');

// Check if venv exists
if (!fs.existsSync(venvPython)) {
  console.error('Error: Python virtual environment not found');
  console.error('Please run: npm run install:backend');
  process.exit(1);
}

// Check if rebuild script exists
if (!fs.existsSync(rebuildScript)) {
  console.error('Error: rebuild_containers.py not found');
  process.exit(1);
}

// Run the rebuild script
console.log('Rebuilding Docker containers...\n');

const rebuild = spawn(venvPython, [rebuildScript], {
  cwd: backendDir,
  stdio: 'inherit',
  shell: isWindows
});

rebuild.on('error', (err) => {
  console.error('Failed to start rebuild:', err);
  process.exit(1);
});

rebuild.on('close', (code) => {
  process.exit(code || 0);
});

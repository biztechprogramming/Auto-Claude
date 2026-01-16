#!/usr/bin/env node
/**
 * Cross-platform E2E test runner for Docker integration tests
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const backendDir = path.join(__dirname, '..', 'apps', 'backend');
const testsDir = path.join(__dirname, '..', 'tests');
const testFile = path.join(testsDir, 'test_docker_e2e.py');

// Determine Python executable path based on platform
const isWindows = process.platform === 'win32';
const pythonPath = isWindows
  ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
  : path.join(backendDir, '.venv', 'bin', 'python');

// Check if virtual environment exists
if (!fs.existsSync(pythonPath)) {
  console.error('Error: Python virtual environment not found.');
  console.error('Please run: npm run install:backend');
  process.exit(1);
}

// Check if test file exists
if (!fs.existsSync(testFile)) {
  console.error(`Error: Test file not found: ${testFile}`);
  process.exit(1);
}

console.log('Running Docker E2E tests...\n');

// Run pytest with verbose and show output flags
// Use --collect-only to verify only E2E tests are selected
const pytest = spawn(
  pythonPath,
  ['-m', 'pytest', testFile, '-v', '-s', '--tb=short'],
  {
    cwd: path.join(__dirname, '..'),  // Run from project root
    stdio: 'inherit',
    env: { ...process.env }
  }
);

pytest.on('close', (code) => {
  process.exit(code);
});

pytest.on('error', (err) => {
  console.error('Failed to run tests:', err);
  process.exit(1);
});

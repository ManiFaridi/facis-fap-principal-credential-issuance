// Copyright (c) 2026 Contributors to this project.
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
test('Docker Hub publication validates source, archives and immutable existing tags', () => {
  const result = spawnSync('python3', ['-B', '-m', 'unittest', 'discover', '-s', 'test/publication', '-p', 'test_*.py'],
    { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stderr, /Ran 9 tests/);
});

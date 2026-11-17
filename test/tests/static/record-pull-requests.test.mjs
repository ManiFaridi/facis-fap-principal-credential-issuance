// Copyright (c) 2026 LEANEA GmbH and others.
//
// This program and the accompanying materials are made available under the
// terms of the Apache License, Version 2.0 which is available at
// https://www.apache.org/licenses/LICENSE-2.0.
//
// SPDX-License-Identifier: Apache-2.0
//
// Prepared with AI-assisted tools and reviewed by the author.
// Assisted-by: AI
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import {
  closedIssues,
  recordAll,
  reviewRecord,
  templateField
} from '../../../tools/record-pull-requests.mjs';
const body = [
  'Work package / item: R2-6',
  'Closes issues: #10, #11, #12',
  'Related issues (not closed by this pull request): #30',
  'Review started (date, time, time zone): 2026-11-11 09:10 CET',
  'Review completed (date, time, time zone): <filled by the reviewer>'
].join('\n');
const pr = (extra = {}) => ({
  number: 41,
  html_url: 'https://github.com/example/repo/pull/41',
  user: { login: 'author' },
  body,
  additions: 112,
  deletions: 10,
  changed_files: 9,
  state: 'closed',
  merged_at: '2026-11-12T15:00:00Z',
  merged_by: { login: 'committer' },
  ...extra
});
const review = (login, state, at) => ({ user: { login }, state, submitted_at: at });
test('template fields are read and placeholders are not taken as values', () => {
  assert.equal(templateField(body, 'Review started'), '2026-11-11 09:10 CET');
  assert.equal(templateField(body, 'Review completed'), null);
  assert.equal(templateField(body, 'Named reviewer'), null);
});
test('only closing references count as closed issues', () => {
  assert.deepEqual(closedIssues(body), [10, 11, 12]);
  assert.deepEqual(closedIssues('Fixes #3 and #2\nSee #9'), [2, 3]);
  assert.deepEqual(closedIssues(''), []);
});
test('a review record needs an approval by someone other than the author', () => {
  assert.equal(reviewRecord(pr(), [review('author', 'APPROVED', '2026-11-11T10:00:00Z')]), null);
  assert.equal(reviewRecord(pr(), [review('reviewer', 'COMMENTED', '2026-11-11T10:00:00Z')]), null);
  const record = reviewRecord(pr(), [
    review('reviewer', 'CHANGES_REQUESTED', '2026-11-11T10:00:00Z'),
    review('author', 'COMMENTED', '2026-11-11T11:00:00Z'),
    review('reviewer', 'APPROVED', '2026-11-12T08:00:00Z')
  ]);
  assert.deepEqual(record, {
    reviewer: 'reviewer',
    firstReviewSubmittedAt: '2026-11-11T10:00:00Z',
    approvedAt: '2026-11-12T08:00:00Z',
    reviewsByOthers: 2,
    reviewStartedStated: '2026-11-11 09:10 CET',
    reviewCompletedStated: null
  });
});
test('items without a pull request number stay as planned; open pull requests are not merged', () => {
  const document = {
    items: [
      { id: 'R2-6', plannedReviewer: 'Reviewer', issues: [], reviewRecord: null, mergedAt: null },
      { id: 'R2-7', plannedReviewer: 'Reviewer', issues: [], reviewRecord: null, mergedAt: null }
    ]
  };
  const open = pr({ state: 'open', merged_at: null, merged_by: null });
  const result = recordAll(document, { 'R2-6': 41 }, () => ({ pr: open, reviews: [] }));
  assert.deepEqual(result.items[1], document.items[1]);
  const item = result.items[0];
  assert.equal(item.status, 'open on GitHub');
  assert.equal(item.mergedAt, null);
  assert.equal(item.mergedBy, null);
  assert.equal(item.reviewRecord, null);
  assert.deepEqual(item.issues, [10, 11, 12]);
  assert.deepEqual(item.sizeOnGitHub, { added: 112, removed: 10, files: 9 });
  assert.equal(item.pullRequest.number, 41);
  const merged = recordAll(document, { 'R2-6': 41 }, () => ({ pr: pr(), reviews: [review('reviewer', 'APPROVED',
    '2026-11-12T08:00:00Z')] })).items[0];
  assert.equal(merged.status, 'merged');
  assert.equal(merged.mergedBy, 'committer');
  assert.equal(merged.reviewRecord.reviewer, 'reviewer');
});
test('the CLI records paginated reviews without requiring a newer gh --slurp flag', () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'pci-record-cli-'));
  try {
    const bin = path.join(temporary, 'bin');
    fs.mkdirSync(bin);
    const fake = path.join(bin, 'gh');
    const program = [
      '#!/usr/bin/env python3',
      'import json,sys',
      'from urllib.parse import parse_qs,urlsplit',
      'if "--slurp" in sys.argv: raise SystemExit(2)',
      'resource=sys.argv[-1]',
      'if "/reviews" in resource:',
      ' page=int(parse_qs(urlsplit(resource).query).get("page",["1"])[0])',
      ' review={"user":{"login":"reviewer"},"state":"COMMENTED","submitted_at":"2026-11-11T10:00:00Z"}',
      ' result=[review]*100 if page==1 else [{**review,"state":"APPROVED","submitted_at":"2026-11-12T08:00:00Z"}]',
      'else:',
      ' result={"number":40,"html_url":"https://github.com/example/repository/pull/40","user":{"login":"author"},"body":"Closes #3","additions":12,"deletions":2,"changed_files":1,"state":"open","merged_at":None}',
      'print(json.dumps(result))',
      ''
    ].join('\n');
    fs.writeFileSync(fake, program, { mode: 0o700 });
    const file = path.join(temporary, 'records.json');
    const map = path.join(temporary, 'map.json');
    fs.writeFileSync(file, JSON.stringify({ items: [{ id: 'R1-1' }] }));
    fs.writeFileSync(map, JSON.stringify({ 'R1-1': 40 }));
    const tool = fileURLToPath(new URL('../../../tools/record-pull-requests.mjs', import.meta.url));
    const result = spawnSync(process.execPath, [tool, '--repo', 'example/repository', '--map', map, '--file', file],
      { encoding: 'utf8', env: { ...process.env, PATH: bin + path.delimiter + process.env.PATH } });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    const item = JSON.parse(fs.readFileSync(file, 'utf8')).items[0];
    assert.equal(item.reviewRecord.reviewsByOthers, 101);
    assert.equal(item.reviewRecord.approvedAt, '2026-11-12T08:00:00Z');
    assert.equal(item.mergedAt, null);
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
});

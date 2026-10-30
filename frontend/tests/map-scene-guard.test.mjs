import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

// Native dialogs make the surrounding Stop button inert; protect every route into that same modal.
test('scene tools cannot open or remain modal while physical controls are read-only',()=>{
  const source=readFileSync(new URL('../src/MapScene.tsx',import.meta.url),'utf8');
  const buttons=[...source.matchAll(/<button\b[^>]*\bonClick=\{\(\) => openTools\('[^']+'\)\}[^>]*>/g)].map(match=>match[0]);
  assert.equal(buttons.length,1,'Image tools is the toolbar entry point; the floating registration card was removed');
  for(const button of buttons) assert.match(button,/disabled=\{readOnly \|\| Boolean\(busy\)\}/);
  assert.match(source,/const openTools = [^\n]*if \(readOnly \|\| busy\) return;/);
  assert.match(source,/lastToolsRequest\.current = openToolsRequest;[\s\S]*?if \(readOnly \|\| busy\) return;/);
  assert.match(source,/if \(readOnly\) \{\s*if \(dialog\.open\) dialog\.close\(\);\s*if \(expanded\) setExpanded\(false\);\s*return;\s*\}/);
  assert.match(source,/\}, \[expanded, readOnly\]\);/);
});

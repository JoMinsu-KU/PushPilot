import { copyFile, mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dependency = path.join(root, 'node_modules', 'three');
const metadata = JSON.parse(await readFile(path.join(dependency, 'package.json'), 'utf8'));
if (metadata.version !== '0.160.0') throw new Error('Review the city decoder assets before changing the pinned Three.js version.');
const target = path.join(root, 'public', 'vendor', 'draco');
await mkdir(target, { recursive: true });
for (const filename of ['draco_decoder.js', 'draco_decoder.wasm', 'draco_wasm_wrapper.js']) {
  await copyFile(path.join(dependency, 'examples', 'jsm', 'libs', 'draco', 'gltf', filename), path.join(target, filename));
}
console.log('Local Draco decoder assets prepared. Private city artwork is installed separately.');

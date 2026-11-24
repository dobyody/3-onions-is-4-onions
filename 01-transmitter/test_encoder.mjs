// Reference-vector check, no camera needed.
// Runs the exact encoder embedded in index.html (<script id="encoder">).
// Run from the project root: node 01-transmitter/test_encoder.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, 'index.html'), 'utf8');
const m = html.match(/<script id="encoder">([\s\S]*?)<\/script>/);
if (!m) { console.error('FAIL  no <script id="encoder"> block in index.html'); process.exit(1); }
const sandbox = { self: {} };
vm.runInNewContext(m[1], sandbox);
const enc = sandbox.self.RSEncoder;
const fixture = JSON.parse(readFileSync(join(here, '..', 'fixtures', 'packet-v1.json'), 'utf8'));

let failures = 0;
function check(name, ok, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + detail : ''}`);
  if (!ok) failures++;
}
function throws(fn) {
  try { fn(); return false; } catch { return true; }
}

const ascii = (s) => Array.from(s, (c) => c.charCodeAt(0));
check('CRC check value crc16("123456789") == 0x29B1',
  enc.crc16ccittFalse(ascii('123456789')) === 0x29b1);

const out = enc.encode(fixture.payload_ascii);
const bits = Array.from(out.bits);
check('packet_hex matches fixture', out.packet_hex === fixture.packet_hex, out.packet_hex);
check('crc_hex matches fixture', out.crc_hex === fixture.crc_hex, out.crc_hex);
check(`bit count == ${fixture.bits.length}`, bits.length === fixture.bits.length, String(bits.length));
const firstDiff = bits.findIndex((b, i) => b !== fixture.bits[i]);
check('bits match fixture element-wise', firstDiff === -1 && bits.length === fixture.bits.length,
  firstDiff === -1 ? '' : `first diff at ${firstDiff}`);

check('rejects empty payload', throws(() => enc.buildPacket('')));
check('rejects 17-char payload', throws(() => enc.buildPacket('A'.repeat(17))));
check('accepts 16-char payload', !throws(() => enc.buildPacket('A'.repeat(16))));
check('rejects non-printable', throws(() => enc.buildPacket('HI\n')));
check('rejects non-ASCII', throws(() => enc.buildPacket('HÉ')));

console.log(failures ? `\n${failures} check(s) FAILED` : '\nALL PASS');
process.exit(failures ? 1 : 0);

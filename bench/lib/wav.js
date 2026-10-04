// Duration of a PCM WAV file from its header (used for cost estimates and result files).
const fs = require('fs');

function wavSeconds(file) {
  const buf = fs.readFileSync(file);
  if (buf.toString('ascii', 0, 4) !== 'RIFF' || buf.toString('ascii', 8, 12) !== 'WAVE') {
    throw new Error(`${file}: not a WAV file`);
  }
  let byteRate = null;
  for (let off = 12; off + 8 <= buf.length;) {
    const id = buf.toString('ascii', off, off + 4);
    const size = buf.readUInt32LE(off + 4);
    if (id === 'fmt ') byteRate = buf.readUInt32LE(off + 16);
    if (id === 'data') {
      if (!byteRate) throw new Error(`${file}: data chunk before fmt chunk`);
      return Math.min(size, buf.length - off - 8) / byteRate;
    }
    off += 8 + size + (size % 2);
  }
  throw new Error(`${file}: no data chunk`);
}

// A silent mono 16 kHz 16-bit WAV of the given length (for tests).
function silentWav(seconds, rate = 16000) {
  const data = Math.round(seconds * rate) * 2;
  const b = Buffer.alloc(44 + data);
  b.write('RIFF', 0); b.writeUInt32LE(36 + data, 4); b.write('WAVE', 8);
  b.write('fmt ', 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22);
  b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
  b.write('data', 36); b.writeUInt32LE(data, 40);
  return b;
}

module.exports = { wavSeconds, silentWav };

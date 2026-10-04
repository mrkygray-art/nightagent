// Text normalization shared by validation and scoring.
//
// Rule (spec section 18): references are written as spoken words, so transcripts
// are converted digits-to-words. "12" -> "twelve", "9,000" -> "nine thousand",
// "2.8" -> "two point eight", "2nd" -> "second", "Cat6" -> "cat six", "2:00" -> "two".
// Known gap: grouped readings ("ninety-three hundred" for 9300) aren't produced; the
// dataset avoids them, and the validator rejects digits in references.

const ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
  'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'];
const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];
const SCALES = [[1e9, 'billion'], [1e6, 'million'], [1e3, 'thousand']];
const ORDINAL = { one: 'first', two: 'second', three: 'third', five: 'fifth', eight: 'eighth', nine: 'ninth', twelve: 'twelfth' };

function under1000(n) {
  const words = [];
  if (n >= 100) { words.push(ONES[Math.floor(n / 100)], 'hundred'); n %= 100; }
  if (n >= 20) { words.push(TENS[Math.floor(n / 10)]); n %= 10; if (n) words.push(ONES[n]); }
  else if (n > 0) words.push(ONES[n]);
  return words;
}

function integerWords(digits) {
  // Leading zeros ("007") are read digit by digit
  if (digits.length > 1 && digits[0] === '0') return [...digits].map((d) => ONES[d]).join(' ');
  let n = Number(digits);
  if (!Number.isSafeInteger(n)) return [...digits].map((d) => ONES[d]).join(' ');
  if (n === 0) return 'zero';
  const words = [];
  for (const [size, name] of SCALES) {
    if (n >= size) { words.push(...under1000(Math.floor(n / size)), name); n %= size; }
  }
  words.push(...under1000(n));
  return words.join(' ');
}

function ordinalWords(digits) {
  const words = integerWords(digits).split(' ');
  const last = words.pop();
  const ord = ORDINAL[last] || (last.endsWith('y') ? `${last.slice(0, -1)}ieth` : `${last}th`);
  return [...words, ord].join(' ');
}

function numbersToWords(text) {
  return text
    .replace(/(\d),(?=\d{3}\b)/g, '$1')                        // 9,000 -> 9000
    .replace(/\b(\d{1,2}):00\b/g, '$1')                        // 2:00 -> 2
    .replace(/(\d+)\.(\d+)/g, (_, a, b) => `${a} point ${[...b].join(' ')}`) // 2.8 -> 2 point 8
    .replace(/\b(\d+)(st|nd|rd|th)\b/gi, (_, d) => ` ${ordinalWords(d)} `)
    .replace(/(\p{L})(?=\d)|(\d)(?=\p{L})/gu, '$1$2 ')        // cat6 -> cat 6, 6a -> 6 a
    .replace(/\d+/g, (d) => ` ${integerWords(d)} `);
}

function normalize(text) {
  return numbersToWords(String(text ?? '').toLowerCase())
    .replace(/%/g, ' percent ')
    .replace(/[-–—/_]/g, ' ')          // hyphens and slashes separate words: "J-hook" -> "j hook"
    .replace(/['’]/g, '')              // apostrophes join: "won't" -> "wont"
    .replace(/[^\p{L}\p{N}\s]/gu, ' ') // any other punctuation becomes a space
    .replace(/\s+/g, ' ')
    .trim();
}

const words = (normalized) => (normalized ? normalized.split(' ') : []);

// Non-overlapping whole-word matches of any of `phrases` in `tokens`, longest phrase first.
// Returns [{ start, end }] word spans (end exclusive), in text order.
function findPhrases(tokens, phrases) {
  const used = new Array(tokens.length).fill(false);
  const spans = [];
  const sorted = [...new Set(phrases)].map(words).filter((p) => p.length).sort((a, b) => b.length - a.length);
  for (const p of sorted) {
    for (let i = 0; i + p.length <= tokens.length; i++) {
      if (p.every((w, j) => tokens[i + j] === w && !used[i + j])) {
        for (let j = 0; j < p.length; j++) used[i + j] = true;
        spans.push({ start: i, end: i + p.length });
        i += p.length - 1;
      }
    }
  }
  return spans.sort((a, b) => a.start - b.start);
}

// Number of times any alias appears in normalized text, as whole words.
const countPhrases = (text, phrases) => findPhrases(words(text), phrases).length;

module.exports = { normalize, words, findPhrases, countPhrases, integerWords };

// Text normalization shared by validation and scoring.
// Build step 1 covers casing, punctuation, and whitespace. Number handling
// (digits to words, "Cat6" to "cat six") is added with the scorer in step 2.

function normalize(text) {
  return String(text ?? '')
    .toLowerCase()
    .replace(/[-–—/_]/g, ' ')        // hyphens and slashes separate words: "J-hook" -> "j hook"
    .replace(/['’]/g, '')            // apostrophes join: "won't" -> "wont"
    .replace(/[^\p{L}\p{N}\s]/gu, ' ') // any other punctuation becomes a space
    .replace(/\s+/g, ' ')
    .trim();
}

// Number of times `phrase` appears in `text` as whole words (both already normalized).
function countPhrase(text, phrase) {
  if (!phrase) return 0;
  const words = text ? text.split(' ') : [];
  const target = phrase.split(' ');
  let count = 0;
  for (let i = 0; i + target.length <= words.length; i++) {
    if (target.every((w, j) => words[i + j] === w)) { count++; i += target.length - 1; }
  }
  return count;
}

module.exports = { normalize, countPhrase };

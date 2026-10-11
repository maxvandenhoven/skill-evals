# Spec: unicode slugs

- Accented characters must be transliterated to ASCII ("Crème" -> "creme").
- Slugs must be at most `max_length` characters (default 60).
- Truncation must never cut a word in half: cut at the last `-` before the limit.

const quotePairs: Array<[string, string]> = [
  ['"', '"'],
  ["'", "'"],
  ['“', '”'],
  ['「', '」'],
  ['『', '』'],
]

export const cleanLearningSheetText = (value: unknown): string => {
  let text = String(value ?? '').replace(/^\uFEFF/, '').trim()
  let changed = true
  while (text.length >= 2 && changed) {
    changed = false
    for (const [opening, closing] of quotePairs) {
      if (text.startsWith(opening) && text.endsWith(closing)) {
        text = text.slice(opening.length, text.length - closing.length).trim()
        changed = true
        break
      }
    }
  }
  return text
}

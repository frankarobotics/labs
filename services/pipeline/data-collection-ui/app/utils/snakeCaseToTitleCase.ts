export default function snakeCaseToTitleCase(word: string | undefined) {
  if (!word) return ''
  return word
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

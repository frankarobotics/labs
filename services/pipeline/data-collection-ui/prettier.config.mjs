/**
 * @type {import('prettier').Config}
 */
export default {
  trailingComma: 'all',
  tabWidth: 2,
  semi: false,
  singleQuote: true,
  jsxSingleQuote: true,
  printWidth: 120,
  arrowParens: 'always',
  plugins: ['prettier-plugin-tailwindcss'],
}

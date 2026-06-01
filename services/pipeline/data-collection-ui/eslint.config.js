import { defineConfig } from '@eslint/config-helpers'
import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import simpleImportSort from 'eslint-plugin-simple-import-sort'
import globals from 'globals'
import ts from 'typescript-eslint'

export default defineConfig([
  {
    ignores: ['dist/**', 'build/**', 'coverage/**', 'node_modules/**', '.react-router/**'],
  },

  { settings: { react: { version: 'detect' } } },
  js.configs.recommended,

  ...ts.configs.recommended,

  react.configs.flat.recommended,
  react.configs.flat['jsx-runtime'],
  reactHooks.configs['recommended-latest'],

  {
    files: ['**/*.{ts,tsx,js,jsx}'],
    plugins: {
      'simple-import-sort': simpleImportSort,
    },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
    },
    rules: {
      'simple-import-sort/imports': 'error',
      'simple-import-sort/exports': 'error',

      'react/jsx-no-useless-fragment': 'warn',
    },
  },

  {
    files: ['server.js'],
    languageOptions: {
      globals: {
        ...globals.node,
        ...globals.es2021,
      },
    },
  },

  {
    rules: {},
  },

  prettier,
])

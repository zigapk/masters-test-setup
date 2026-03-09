import { defineConfig } from 'rolldown'

export default defineConfig({
  input: {
    'follow': 'src/follow.tsx',
    'follow-using-error-boundary': 'src/follow-using-error-boundary.tsx',
  },
  platform: 'node',
  // serialport must stay external -- it uses native C++ addons (.node files)
  // loaded via node-gyp-build which relies on __dirname to find them.
  external: [/^serialport/],
  resolve: {
    tsconfigFilename: 'tsconfig.json',
  },
  output: {
    dir: 'dist',
    format: 'esm',
    entryFileNames: '[name].mjs',
  },
})

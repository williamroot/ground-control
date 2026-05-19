// Provide Nitro/h3 auto-import globals so server middleware can be unit-tested
// without a full Nuxt/Nitro boot. Only imports from the h3 package that Nuxt
// already ships — no extra production deps.
import {
  defineEventHandler,
  getRequestHeader,
} from 'h3'

Object.assign(globalThis, {
  defineEventHandler,
  getRequestHeader,
  // sidecarFetch is only called at runtime; stub it so the module loads cleanly.
  sidecarFetch: () => Promise.resolve({ status: 500, data: null, setCookie: [] }),
})

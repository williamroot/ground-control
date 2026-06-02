// Globals h3/Nitro p/ unit-test de server utils sem boot completo do Nuxt
// (só do pacote h3 que o Nuxt já traz — sem deps de produção extras).
import {
  defineEventHandler,
  getRequestHeader,
} from 'h3'

Object.assign(globalThis, {
  defineEventHandler,
  getRequestHeader,
  sidecarFetch: () => Promise.resolve({ status: 500, data: null, setCookie: [] }),
})

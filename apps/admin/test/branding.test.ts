// Spec #3, V4 — validação pura do editor de identidade visual.
import { describe, expect, it } from 'vitest'
import {
  buildBrandingPayload,
  emptyBrandingDraft,
  isBrandingValid,
  parseValidationErrors,
  validateBrandingDraft,
  validateHexColor,
  validateLogoUrl,
} from '../composables/useBranding'

describe('validateHexColor', () => {
  it('aceita hex de 6 dígitos maiúsculo ou minúsculo', () => {
    expect(validateHexColor('#4f46e5')).toBe(true)
    expect(validateHexColor('#4F46E5')).toBe(true)
  })

  it('rejeita formatos inválidos', () => {
    expect(validateHexColor('4f46e5')).toBe(false)
    expect(validateHexColor('#fff')).toBe(false)
    expect(validateHexColor('#gggggg')).toBe(false)
    expect(validateHexColor('')).toBe(false)
  })
})

describe('validateLogoUrl', () => {
  it('vazio é válido (opcional)', () => {
    expect(validateLogoUrl('')).toBe(true)
    expect(validateLogoUrl('   ')).toBe(true)
  })

  it('exige https://', () => {
    expect(validateLogoUrl('https://exemplo.com/logo.png')).toBe(true)
    expect(validateLogoUrl('http://exemplo.com/logo.png')).toBe(false)
    expect(validateLogoUrl('exemplo.com/logo.png')).toBe(false)
  })

  it('rejeita acima de 500 caracteres', () => {
    const long = `https://exemplo.com/${'a'.repeat(500)}`
    expect(validateLogoUrl(long)).toBe(false)
  })
})

describe('validateBrandingDraft', () => {
  it('rascunho vazio tem erro de nome (cores default já são válidas)', () => {
    const errors = validateBrandingDraft(emptyBrandingDraft())
    expect(errors.display_name).toBeTruthy()
    expect(errors.primary_color).toBeUndefined()
    expect(errors.accent_color).toBeUndefined()
  })

  it('rascunho válido não tem erros', () => {
    const draft = {
      ...emptyBrandingDraft(),
      display_name: 'Cliente Exemplo',
    }
    expect(isBrandingValid(draft)).toBe(true)
    expect(validateBrandingDraft(draft)).toEqual({})
  })

  it('detecta cor e logo inválidos ao mesmo tempo', () => {
    const draft = {
      ...emptyBrandingDraft(),
      display_name: 'Cliente Exemplo',
      primary_color: 'red',
      logo_url: 'http://inseguro.com/logo.png',
    }
    const errors = validateBrandingDraft(draft)
    expect(errors.primary_color).toBeTruthy()
    expect(errors.logo_url).toBeTruthy()
    expect(isBrandingValid(draft)).toBe(false)
  })
})

describe('buildBrandingPayload', () => {
  it('normaliza espaços e converte logo_url vazio para null', () => {
    const draft = {
      display_name: '  Cliente Exemplo  ',
      primary_color: ' #4f46e5 ',
      accent_color: '#4338ca',
      logo_url: '   ',
      default_theme: 'dark' as const,
    }
    const payload = buildBrandingPayload(draft)
    expect(payload.display_name).toBe('Cliente Exemplo')
    expect(payload.primary_color).toBe('#4f46e5')
    expect(payload.logo_url).toBeNull()
    expect(payload.default_theme).toBe('dark')
  })

  it('mantém logo_url quando preenchida', () => {
    const draft = { ...emptyBrandingDraft(), logo_url: 'https://exemplo.com/logo.png' }
    expect(buildBrandingPayload(draft).logo_url).toBe('https://exemplo.com/logo.png')
  })
})

describe('parseValidationErrors', () => {
  it('mapeia erros de Pydantic (array) para campo -> mensagem', () => {
    const detail = [
      { loc: ['body', 'primary_color'], msg: 'string does not match regex' },
      { loc: ['body', 'logo_url'], msg: 'must start with https://' },
    ]
    const errors = parseValidationErrors(detail)
    expect(errors.primary_color).toBe('string does not match regex')
    expect(errors.logo_url).toBe('must start with https://')
  })

  it('mensagem de domínio (string) vira erro geral na chave vazia', () => {
    const errors = parseValidationErrors('tenant_not_found')
    expect(errors['']).toBe('tenant_not_found')
  })

  it('detail ausente/desconhecido não quebra', () => {
    expect(parseValidationErrors(undefined)).toEqual({})
    expect(parseValidationErrors(null)).toEqual({})
  })
})

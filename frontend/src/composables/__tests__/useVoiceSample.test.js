// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { isCurrentSample, playSample, stopCurrentSample } from '@/composables/useVoiceSample.js'

describe('useVoiceSample', () => {
  beforeEach(() => {
    global.Audio = class {
      constructor(src) {
        this.src = src
        this.paused = false
      }
      play() { this.paused = false; return Promise.resolve() }
      pause() { this.paused = true }
    }
  })

  it('播新的会先停掉上一个', () => {
    const a = playSample('/a.mp3')
    const b = playSample('/b.mp3')
    expect(a.paused).toBe(true)
    expect(b.paused).toBe(false)
    expect(isCurrentSample(b)).toBe(true)
    expect(isCurrentSample(a)).toBe(false)
  })

  it('stopCurrentSample 停掉当前', () => {
    const a = playSample('/a.mp3')
    stopCurrentSample()
    expect(a.paused).toBe(true)
    expect(isCurrentSample(a)).toBe(false)
  })
})

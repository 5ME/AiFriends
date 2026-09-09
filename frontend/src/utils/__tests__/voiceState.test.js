import { describe, it, expect } from 'vitest'
import { voiceReducer, VOICE_STATES, VOICE_EVENTS } from '../voiceState'

const S = VOICE_STATES, E = VOICE_EVENTS

describe('voiceReducer（LD §6 转移表全行 + 标注的补全行）', () => {
  it('idle + CLICK_MIC → listening', () => {
    expect(voiceReducer(S.IDLE, E.CLICK_MIC)).toBe(S.LISTENING)
  })
  it('listening + SPEECH_START → listening（打断 TTS 不换态）', () => {
    expect(voiceReducer(S.LISTENING, E.SPEECH_START)).toBe(S.LISTENING)
  })
  it('listening + SPEECH_END → transcribing', () => {
    expect(voiceReducer(S.LISTENING, E.SPEECH_END)).toBe(S.TRANSCRIBING)
  })
  it('listening + CANCEL → idle（Esc/✕/再点🎤）', () => {
    expect(voiceReducer(S.LISTENING, E.CANCEL)).toBe(S.IDLE)
  })
  it('listening + VAD_INIT_FAILED → vad_failed', () => {
    expect(voiceReducer(S.LISTENING, E.VAD_INIT_FAILED)).toBe(S.VAD_FAILED)
  })
  it('listening + MIC_PERMISSION_DENIED → mic_denied', () => {
    expect(voiceReducer(S.LISTENING, E.MIC_PERMISSION_DENIED)).toBe(S.MIC_DENIED)
  })
  it('transcribing + TRANSCRIPT_TEXT → confirm', () => {
    expect(voiceReducer(S.TRANSCRIBING, E.TRANSCRIPT_TEXT)).toBe(S.CONFIRM)
  })
  it('transcribing + TRANSCRIPT_EMPTY → asr_failed', () => {
    expect(voiceReducer(S.TRANSCRIBING, E.TRANSCRIPT_EMPTY)).toBe(S.ASR_FAILED)
  })
  it('transcribing + ASR_ERROR → asr_failed', () => {
    expect(voiceReducer(S.TRANSCRIBING, E.ASR_ERROR)).toBe(S.ASR_FAILED)
  })
  it('transcribing + CANCEL → idle（丢弃结果）', () => {
    expect(voiceReducer(S.TRANSCRIBING, E.CANCEL)).toBe(S.IDLE)
  })
  it('confirm + SEND → idle', () => {
    expect(voiceReducer(S.CONFIRM, E.SEND)).toBe(S.IDLE)
  })
  it('confirm + CLICK_MIC → listening（覆盖重录）', () => {
    expect(voiceReducer(S.CONFIRM, E.CLICK_MIC)).toBe(S.LISTENING)
  })
  it('confirm + EDIT_TEXT → confirm', () => {
    expect(voiceReducer(S.CONFIRM, E.EDIT_TEXT)).toBe(S.CONFIRM)
  })
  it.each([S.VAD_FAILED, S.MIC_DENIED, S.ASR_FAILED])('%s + RETRY → listening', (state) => {
    expect(voiceReducer(state, E.RETRY)).toBe(S.LISTENING)
  })
  // 补全行：LD §6 表未覆盖——错误态下用户仍可打字直接发送，SEND 一律回 idle
  it.each([S.IDLE, S.VAD_FAILED, S.MIC_DENIED, S.ASR_FAILED])('%s + SEND → idle（补全行：错误态可打字发送）', (state) => {
    expect(voiceReducer(state, E.SEND)).toBe(S.IDLE)
  })
  it('未知事件 → 原状态（no-op）', () => {
    expect(voiceReducer(S.IDLE, 'NOPE')).toBe(S.IDLE)
    expect(voiceReducer(S.CONFIRM, 'NOPE')).toBe(S.CONFIRM)
  })
  it('未知状态 → 原状态（no-op）', () => {
    expect(voiceReducer('ghost', E.SEND)).toBe('ghost')
  })
})

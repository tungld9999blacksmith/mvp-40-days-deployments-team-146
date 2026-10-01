import { describe, expect, it } from 'vitest'
import { SseParser } from './sse'

describe('SseParser', () => {
  it('parses named events and JSON data', () => {
    const parser = new SseParser()
    const events = parser.push('event: token\ndata: {"delta":"Xin "}\n\nevent: token\ndata: {"delta":"chào"}\n\n')
    expect(events).toEqual([
      { event: 'token', data: '{"delta":"Xin "}', id: undefined },
      { event: 'token', data: '{"delta":"chào"}', id: undefined },
    ])
  })

  it('keeps an event split across chunks until it is complete', () => {
    const parser = new SseParser()
    expect(parser.push('event: message.completed\nda')).toEqual([])
    expect(parser.push('ta: {"message":{"id":"1"}}\n')).toEqual([])
    expect(parser.push('\n')).toEqual([{ event: 'message.completed', data: '{"message":{"id":"1"}}', id: undefined }])
  })

  it('joins multi-line data with newlines', () => {
    const parser = new SseParser()
    expect(parser.push('data: line one\ndata: line two\n\n')).toEqual([{ event: 'message', data: 'line one\nline two', id: undefined }])
  })

  it('ignores keep-alive comments', () => {
    const parser = new SseParser()
    expect(parser.push(': ping\n\n')).toEqual([])
    expect(parser.push(': ping\nevent: status\ndata: {"stage":"retrieving"}\n\n')).toEqual([
      { event: 'status', data: '{"stage":"retrieving"}', id: undefined },
    ])
  })

  it('handles CRLF, including a CR at the end of one chunk and LF at the start of the next', () => {
    const parser = new SseParser()
    expect(parser.push('event: token\r\ndata: {"delta":"a"}\r')).toEqual([])
    expect(parser.push('\n\r\n')).toEqual([{ event: 'token', data: '{"delta":"a"}', id: undefined }])
  })

  it('flushes a last event without a trailing blank line', () => {
    const parser = new SseParser()
    parser.push('event: error\ndata: {"code":"AGENT_FAILED"}')
    expect(parser.flush()).toEqual([{ event: 'error', data: '{"code":"AGENT_FAILED"}', id: undefined }])
  })
})

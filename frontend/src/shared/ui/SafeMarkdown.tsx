import { Fragment, type ReactNode } from 'react'

/** `**bold**` → <strong>. Everything is rendered as text nodes: no raw HTML, no links. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={`${keyPrefix}-${index}`} className="font-semibold text-foreground">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <Fragment key={`${keyPrefix}-${index}`}>{part}</Fragment>
    ),
  )
}

const BULLET = /^\s*(?:[-*•])\s+(.*)$/
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/

/**
 * Minimal safe markdown for assistant answers (US-025 FE §4.2): paragraphs, bullet and
 * numbered lists, bold, line breaks. Built from React elements — never innerHTML.
 */
export default function SafeMarkdown({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  let paragraph: string[] = []
  let list: { ordered: boolean; items: string[] } | null = null

  const flushParagraph = () => {
    if (!paragraph.length) return
    const key = `p-${blocks.length}`
    blocks.push(
      <p key={key}>
        {paragraph.map((line, index) => (
          <Fragment key={index}>
            {index > 0 && <br />}
            {inline(line, `${key}-${index}`)}
          </Fragment>
        ))}
      </p>,
    )
    paragraph = []
  }
  const flushList = () => {
    if (!list) return
    const key = `l-${blocks.length}`
    const items = list.items.map((item, index) => <li key={index}>{inline(item, `${key}-${index}`)}</li>)
    blocks.push(
      list.ordered ? (
        <ol key={key} className="list-decimal pl-5 space-y-1">
          {items}
        </ol>
      ) : (
        <ul key={key} className="list-disc pl-5 space-y-1">
          {items}
        </ul>
      ),
    )
    list = null
  }

  for (const line of lines) {
    const bullet = BULLET.exec(line)
    const numbered = bullet ? null : NUMBERED.exec(line)
    if (bullet || numbered) {
      flushParagraph()
      const ordered = Boolean(numbered)
      if (list && list.ordered !== ordered) flushList()
      if (!list) list = { ordered, items: [] }
      list.items.push((bullet ?? numbered)![1])
    } else if (line.trim() === '') {
      flushParagraph()
      flushList()
    } else {
      flushList()
      paragraph.push(line)
    }
  }
  flushParagraph()
  flushList()

  return <div className="space-y-2.5">{blocks}</div>
}

const ENTITIES: Record<string, string> = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&#x27;': "'" }

function decode(text: string): string {
  return text.replace(/&(?:amp|lt|gt|quot|#39|#x27);/g, entity => ENTITIES[entity] ?? entity)
}

/**
 * Search snippet with `<mark>` highlights (US-025 FE §4.7). Only `<mark>` is honoured;
 * every other tag stays escaped text.
 */
export function MarkedSnippet({ html }: { html: string }) {
  const parts = html.split(/(<mark>[\s\S]*?<\/mark>)/g)
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith('<mark>') ? (
          <mark key={index} className="bg-emerald/20 text-emerald-bright rounded px-0.5">
            {decode(part.slice(6, -7))}
          </mark>
        ) : (
          <Fragment key={index}>{decode(part)}</Fragment>
        ),
      )}
    </>
  )
}

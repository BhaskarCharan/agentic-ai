/** One parsed Server-Sent Event: `event: <name>` + `data: <json>`. */
export interface SseEvent {
  event: string;
  data: unknown;
}

/**
 * Read a `text/event-stream` body chunk-by-chunk and yield parsed events.
 *
 * We can't use the browser's `EventSource` here - it only supports GET
 * requests with no custom body, and our chat/resume endpoints need a POST
 * with a JSON body. So instead we read the raw stream from `fetch()` and
 * parse the SSE wire format (`event:` / `data:` lines, events separated by
 * a blank line) by hand.
 */
export async function* readSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<SseEvent> {
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex: number;
    while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);

      const eventLine = rawEvent.split('\n').find((line) => line.startsWith('event:'));
      const dataLine = rawEvent.split('\n').find((line) => line.startsWith('data:'));
      if (!eventLine || !dataLine) continue;

      yield {
        event: eventLine.slice('event:'.length).trim(),
        data: JSON.parse(dataLine.slice('data:'.length).trim()),
      };
    }
  }
}

/** One server-sent event of a chat answer: thread, token, tool, tool_result, done or error. */
export interface ChatStreamEvent {
  event: string;
  data: Record<string, unknown>;
}

/** The events of a text/event-stream body, each as soon as it has fully arrived. */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatStreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      return;
    }
    buffer += decoder.decode(value, { stream: true });
    let end = buffer.indexOf("\n\n");
    while (end !== -1) {
      const event = parseFrame(buffer.slice(0, end));
      buffer = buffer.slice(end + 2);
      if (event !== null) {
        yield event;
      }
      end = buffer.indexOf("\n\n");
    }
  }
}

/** "event: token" plus "data: {...}" lines; null for a frame without data. */
function parseFrame(frame: string): ChatStreamEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      data.push(line.slice("data:".length).trimStart());
    }
  }
  if (data.length === 0) {
    return null;
  }
  const payload: unknown = JSON.parse(data.join("\n"));
  return { event, data: typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>) : {} };
}

import { Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';
import { API_BASE_URL } from './api-config';
import { ChatMessage, PendingInterrupt } from './models';
import { readSseStream } from './sse';

/**
 * Owns the state for whichever conversation is currently open, and drives
 * the two SSE endpoints (/chat, /resume). Everything is exposed as signals
 * so the template can just read them directly.
 */
@Injectable({ providedIn: 'root' })
export class ChatService {
  readonly currentThreadId = signal<string | null>(null);
  readonly messages = signal<ChatMessage[]>([]);
  readonly pendingInterrupt = signal<PendingInterrupt | null>(null);
  readonly isStreaming = signal(false);
  // True only for the gap between sending a message and the first token (or
  // interrupt) coming back - drives the "Thinking..." placeholder. Once
  // anything visible arrives, this flips off even though isStreaming stays
  // true until the turn fully finishes.
  readonly isThinking = signal(false);

  constructor(private readonly api: ApiService) {}

  async loadSession(threadId: string): Promise<void> {
    this.currentThreadId.set(threadId);
    this.pendingInterrupt.set(null);
    const history = await firstValueFrom(this.api.getHistory(threadId));
    this.messages.set(history);
  }

  async sendMessage(text: string): Promise<void> {
    this.messages.update((list) => [...list, { role: 'human', content: text }]);
    await this.streamTurn('/chat', { message: text });
  }

  async resolveInterrupt(approved: boolean): Promise<void> {
    this.pendingInterrupt.set(null);
    await this.streamTurn('/resume', { approved });
  }

  /** POST to `path`, then translate the SSE response into signal updates. */
  private async streamTurn(path: string, body: unknown): Promise<void> {
    const threadId = this.currentThreadId();
    if (!threadId) return;

    this.isStreaming.set(true);
    this.isThinking.set(true);
    try {
      const response = await fetch(`${API_BASE_URL}/sessions/${threadId}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!response.ok || !response.body) {
        this.messages.update((list) => [
          ...list,
          { role: 'ai', content: `Error: request failed (${response.status}).` },
        ]);
        return;
      }

      let aiBubbleStarted = false;
      for await (const evt of readSseStream(response.body.getReader())) {
        if (evt.event === 'token') {
          const chunk = (evt.data as { content: string }).content;
          this.isThinking.set(false);
          if (!aiBubbleStarted) {
            this.messages.update((list) => [...list, { role: 'ai', content: chunk }]);
            aiBubbleStarted = true;
          } else {
            this.messages.update((list) => {
              const updated = [...list];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = { ...last, content: last.content + chunk };
              return updated;
            });
          }
        } else if (evt.event === 'interrupt') {
          this.isThinking.set(false);
          this.pendingInterrupt.set(evt.data as PendingInterrupt);
        }
        // "done" needs no handling - the loop just ends naturally.
      }
    } finally {
      this.isStreaming.set(false);
      this.isThinking.set(false);
    }
  }
}

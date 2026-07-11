import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';
import { ChatService } from './chat.service';
import { ChatSession } from './models';

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly chat = inject(ChatService);

  protected readonly sessions = signal<ChatSession[]>([]);
  protected draft = '';

  async ngOnInit(): Promise<void> {
    await this.refreshSessions();
    const first = this.sessions()[0];
    if (first) {
      await this.chat.loadSession(first.id);
    } else {
      await this.startNewChat();
    }
  }

  async refreshSessions(): Promise<void> {
    this.sessions.set(await firstValueFrom(this.api.listSessions()));
  }

  async startNewChat(): Promise<void> {
    const session = await firstValueFrom(this.api.createSession());
    await this.refreshSessions();
    await this.chat.loadSession(session.id);
  }

  async selectSession(session: ChatSession): Promise<void> {
    if (session.id === this.chat.currentThreadId()) return;
    await this.chat.loadSession(session.id);
  }

  async deleteSession(session: ChatSession, event: Event): Promise<void> {
    event.stopPropagation();
    await firstValueFrom(this.api.deleteSession(session.id));
    await this.refreshSessions();
    if (this.chat.currentThreadId() === session.id) {
      await this.startNewChat();
    }
  }

  async send(): Promise<void> {
    const text = this.draft.trim();
    if (!text || this.chat.isStreaming()) return;
    this.draft = '';
    await this.chat.sendMessage(text);
    await this.refreshSessions(); // picks up the updated `updated_at` ordering
  }

  approveToolCall(): void {
    void this.chat.resolveInterrupt(true);
  }

  declineToolCall(): void {
    void this.chat.resolveInterrupt(false);
  }
}

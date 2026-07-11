import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from './api-config';
import { ChatMessage, ChatSession } from './models';

/**
 * Plain CRUD calls for session management. Ordinary request/response, so
 * HttpClient is fine here - streaming chat lives in ChatService instead,
 * since HttpClient doesn't give us raw access to a fetch ReadableStream.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  listSessions(): Observable<ChatSession[]> {
    return this.http.get<ChatSession[]>(`${API_BASE_URL}/sessions`);
  }

  createSession(title?: string): Observable<ChatSession> {
    return this.http.post<ChatSession>(`${API_BASE_URL}/sessions`, { title });
  }

  getHistory(threadId: string): Observable<ChatMessage[]> {
    return this.http.get<ChatMessage[]>(`${API_BASE_URL}/sessions/${threadId}/history`);
  }

  deleteSession(threadId: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/sessions/${threadId}`);
  }
}

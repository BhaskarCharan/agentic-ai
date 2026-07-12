import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from './api-config';
import { ConnectResponse, IntegrationStatus } from './models';

/**
 * Plain CRUD calls for the Gmail/LinkedIn account-linking panel - same
 * shape as ApiService for sessions, just a different resource.
 */
@Injectable({ providedIn: 'root' })
export class IntegrationsService {
  private readonly http = inject(HttpClient);

  list(): Observable<IntegrationStatus[]> {
    return this.http.get<IntegrationStatus[]>(`${API_BASE_URL}/integrations`);
  }

  connect(toolkit: string): Observable<ConnectResponse> {
    return this.http.post<ConnectResponse>(`${API_BASE_URL}/integrations/${toolkit}/connect`, {});
  }

  disconnect(toolkit: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/integrations/${toolkit}`);
  }
}

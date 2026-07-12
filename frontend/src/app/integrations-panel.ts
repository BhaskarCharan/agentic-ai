import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { IntegrationsService } from './integrations.service';
import { IntegrationStatus } from './models';

const TOOLKIT_LABELS: Record<string, string> = {
  gmail: 'Gmail',
  linkedin: 'LinkedIn',
};

/**
 * Sidebar panel showing which external accounts (Gmail, LinkedIn) are
 * linked via Composio, with a "Connect" button per toolkit that opens the
 * real OAuth consent screen in a new tab - see MULTI_AGENT_ROADMAP.md
 * Phase 1. There's no webhook/polling here: after completing consent in
 * the other tab, the user comes back and clicks "Refresh" to see the
 * updated status, which is enough for a single-user local app.
 */
@Component({
  selector: 'app-integrations-panel',
  imports: [CommonModule],
  templateUrl: './integrations-panel.html',
  styleUrl: './integrations-panel.css',
})
export class IntegrationsPanel implements OnInit {
  private readonly integrations = inject(IntegrationsService);

  protected readonly statuses = signal<IntegrationStatus[]>([]);
  protected readonly connecting = signal<string | null>(null);
  protected readonly disconnecting = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.statuses.set(await firstValueFrom(this.integrations.list()));
  }

  label(toolkit: string): string {
    return TOOLKIT_LABELS[toolkit] ?? toolkit;
  }

  async connect(toolkit: string): Promise<void> {
    this.connecting.set(toolkit);
    try {
      const { redirect_url } = await firstValueFrom(this.integrations.connect(toolkit));
      window.open(redirect_url, '_blank', 'noopener,noreferrer');
    } finally {
      this.connecting.set(null);
    }
  }

  async disconnect(toolkit: string): Promise<void> {
    if (!confirm(`Disconnect ${this.label(toolkit)}? The agent will no longer be able to use it.`)) {
      return;
    }
    this.disconnecting.set(toolkit);
    try {
      await firstValueFrom(this.integrations.disconnect(toolkit));
      await this.refresh();
    } finally {
      this.disconnecting.set(null);
    }
  }
}

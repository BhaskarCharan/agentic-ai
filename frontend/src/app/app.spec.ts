import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { App } from './app';
import { ApiService } from './api.service';

describe('App', () => {
  beforeEach(async () => {
    // Stub ApiService entirely so ngOnInit's session-loading calls never hit
    // the network during tests.
    const apiStub: Partial<ApiService> = {
      listSessions: () => of([]),
      createSession: () => of({ id: 't1', title: 'New conversation', created_at: '', updated_at: '' }),
      getHistory: () => of([]),
    };

    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: ApiService, useValue: apiStub }],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });
});

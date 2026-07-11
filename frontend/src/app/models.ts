// Mirrors backend/src/app/api/schemas.py - keep these two in sync by hand,
// there's no shared codegen between the Python and TypeScript sides here.

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  // Tool messages are filtered out on the backend before they ever reach
  // the frontend - see backend/src/app/api/sessions.py and chat.py.
  role: 'human' | 'ai';
  content: string;
}

// The payload carried by an "interrupt" SSE event - the agent wants to run
// a tool and is waiting for the user to approve/decline it.
export interface PendingInterrupt {
  type: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
}

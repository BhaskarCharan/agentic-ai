"""
Typed shapes for every document this app stores in MongoDB.

There are three collections in the `agentic_ai_chat` database, owned by two
different pieces of code:

  * `sessions`           - owned by US (app/db.py). `SessionDocument` below
                            is the real, enforced shape - db.py always reads
                            and writes through it.
  * `checkpoints`        - owned by LangGraph's `MongoDBSaver`
                            (langgraph-checkpoint-mongodb). It writes these
                            with its own internal (de)serializer; our code
                            never constructs or parses these documents
                            directly, so the two classes below are
                            documentation of the shape, not something we
                            import/use elsewhere.
  * `checkpoint_writes`  - also owned by `MongoDBSaver`, same caveat.

See `app/agent/graph.py` for where the checkpointer is built, and the
docstring on each class below for what the collection is actually for.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# Ours: sessions
# --------------------------------------------------------------------------


class SessionDocument(BaseModel):
    """One document per conversation, in the `sessions` collection.

    This is pure UI-facing metadata - it exists only so the frontend can
    render a sidebar of past conversations without asking LangGraph "list
    me every thread_id you know about" (which its checkpointer doesn't
    support). The actual message content is never stored here; it lives in
    `checkpoints`, keyed by this same id.
    """

    model_config = ConfigDict(populate_by_name=True)

    # Doubles as the LangGraph `thread_id` - deleting a session by this id
    # also means deleting the checkpoints filed under the same thread_id.
    id: str = Field(alias="_id")
    title: str
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# LangGraph-owned: checkpoints
# --------------------------------------------------------------------------


class CheckpointDocument(BaseModel):
    """Reference only - one full snapshot of graph state, in `checkpoints`.

    LangGraph models a graph run as a sequence of "super-steps" (one round
    of node execution). After each super-step, it writes one document here
    containing the *entire* state at that point - every message so far,
    which channels changed, etc. `parent_checkpoint_id` chains each snapshot
    to the one before it, so a thread's full history is a linked list of
    these documents (this is what makes both "replay this conversation from
    scratch" and LangGraph's time-travel/rewind features possible).

    A unique index on `(thread_id, checkpoint_ns, checkpoint_id)` is what
    lets the saver find "the latest checkpoint for this thread" fast.
    """

    id: Any = Field(alias="_id")  # ObjectId, auto-assigned by MongoDB

    # Which conversation this snapshot belongs to - matches SessionDocument.id.
    thread_id: str

    # "" for the main graph; non-empty for a subgraph's own checkpoint
    # sub-stream. We don't use subgraphs, so this is always "" here.
    checkpoint_ns: str

    # Unique, monotonically-sortable id for this specific snapshot.
    checkpoint_id: str

    # The checkpoint_id this one was created from, or null for the first
    # checkpoint in a thread. Forms the history chain described above.
    parent_checkpoint_id: str | None

    # Serialization format used for the `checkpoint`/`metadata` blobs below.
    # We use LangGraph's default, "msgpack" (fast + compact, but opaque -
    # not human-readable in `mongosh` without decoding it in Python).
    type: str

    # Opaque, msgpack-encoded blob: the actual state - message list,
    # per-channel versions, which node is up next, etc. Only
    # `MongoDBSaver`'s serializer ever decodes this.
    checkpoint: bytes

    # Opaque, msgpack-encoded blob: run metadata - `source` (e.g. "input",
    # "loop", "update"), `step` (an incrementing counter), and `parents`
    # (parent checkpoint ids per subgraph namespace).
    metadata: bytes


# --------------------------------------------------------------------------
# LangGraph-owned: checkpoint_writes
# --------------------------------------------------------------------------


class CheckpointWriteDocument(BaseModel):
    """Reference only - one pending write, in `checkpoint_writes`.

    Where `checkpoints` holds a full consolidated snapshot per super-step,
    `checkpoint_writes` holds the *individual* writes each node produced
    during that step, before they get folded into the next checkpoint. This
    is what lets LangGraph resume a step that didn't finish (e.g. our
    `interrupt()` pausing mid-`tools_node`) without losing partial work, and
    is also how our human-in-the-loop flow is physically represented:

      * `channel="__interrupt__"` - the payload `tools_node` handed to
        `interrupt()` (tool name + args), written the moment the graph
        pauses.
      * `channel="__resume__"` - the value your `Command(resume=...)` call
        supplied, written the moment /resume is called.
      * `channel="messages"` - a node's contribution to the running message
        list (e.g. the agent's reply, or a tool's result).
      * `channel="branch:to:agent"` / `"branch:to:tools"` - internal
        routing markers recording which conditional edge fired, so
        LangGraph knows which node to run next on resume.

    A unique index on `(thread_id, checkpoint_ns, checkpoint_id, task_id,
    idx)` identifies exactly one write: `task_id` is the node execution that
    produced it, `idx` its order among that node's writes (a node can write
    to more than one channel).
    """

    id: Any = Field(alias="_id")  # ObjectId, auto-assigned by MongoDB

    thread_id: str
    checkpoint_ns: str
    # Which checkpoint these writes are building on top of.
    checkpoint_id: str

    # Identifies the specific node execution ("task") that produced this
    # write, and where in the graph that task lives.
    task_id: str
    task_path: str

    # Order of this write among possibly-several from the same task.
    idx: int

    # Which state channel this write targets - see the channel list above.
    channel: str

    # Serialization format for `value` (see CheckpointDocument.type).
    type: str

    # Opaque, msgpack-encoded blob: the actual value written to `channel`.
    value: bytes

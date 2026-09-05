import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Send, FileText, Loader2, AlertTriangle, RefreshCw, MessagesSquare } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import clsx from "clsx";

import { api } from "../lib/api.js";
import { useWebSocket } from "../hooks/useWebSocket.js";
import PageHeader from "../components/PageHeader.jsx";
import { useAuth } from "../context/AuthContext.jsx";

/* ── Suggested prompts shown in empty state ─────────────────────────────── */
const SUGGESTED = [
  "What is our termination clause with Vendor X?",
  "How much did we spend with Vendor Y this quarter?",
  "List all invoices with price discrepancies above $500.",
  "Which contracts expire in the next 90 days?",
];

export default function Chat() {
  const { workspaceId } = useAuth();
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState("");
  const [sessionError, setSessionError] = useState(false);
  const bottomRef = useRef(null);
  const streamingBufferRef = useRef("");

  const ensureSession = useMutation({
    mutationFn: async () =>
      (await api.post("/chat/sessions/", { workspace: workspaceId, title: "New chat" })).data,
    onSuccess: (data) => {
      setSessionId(data.id);
      setSessionError(false);
    },
    onError: () => {
      setSessionError(true);
      toast.error("Could not start chat session — please retry");
    },
  });

  useEffect(() => {
    if (!sessionId && workspaceId) ensureSession.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const { send, connected } = useWebSocket(
    sessionId ? `/chat/${sessionId}/` : null,
    (msg) => {
      if (msg.type === "token") {
        streamingBufferRef.current += msg.content;
        setStreaming(streamingBufferRef.current);
      } else if (msg.type === "done") {
        const finalContent = streamingBufferRef.current;
        streamingBufferRef.current = "";
        setStreaming("");
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: finalContent, citations: msg.citations },
        ]);
      } else if (msg.type === "error") {
        streamingBufferRef.current = "";
        setStreaming("");
        toast.error(msg.detail || "Chat error — please try again");
      }
    }
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  function submit(e) {
    e?.preventDefault();
    if (!input.trim() || !connected) return;
    setMessages((prev) => [...prev, { role: "user", content: input }]);
    send({ question: input });
    setInput("");
  }

  function submitSuggestion(text) {
    setInput(text);
    // Let one render cycle set the input, then submit
    setTimeout(() => {
      setMessages((prev) => [...prev, { role: "user", content: text }]);
      send({ question: text });
      setInput("");
    }, 0);
  }

  /* ── Loading state ───────────────────────────────────────────────────── */
  if (ensureSession.isPending && !sessionId) {
    return (
      <div className="flex flex-col h-screen">
        <PageHeader eyebrow="RAG" title="Ask your procurement data" />
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-ink/50">
          <Loader2 size={22} className="animate-spin text-ledgerLight" aria-hidden="true" />
          <span className="text-sm">Starting session…</span>
        </div>
      </div>
    );
  }

  /* ── Error state ─────────────────────────────────────────────────────── */
  if (sessionError && !sessionId) {
    return (
      <div className="flex flex-col h-screen">
        <PageHeader eyebrow="RAG" title="Ask your procurement data" />
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center">
          <AlertTriangle size={22} className="text-critical" aria-hidden="true" />
          <div className="text-sm text-critical">Could not start chat session.</div>
          <button
            onClick={() => { setSessionError(false); ensureSession.mutate(); }}
            className="flex items-center gap-2 px-4 py-2 rounded-md border border-line text-sm text-ink/60 hover:bg-line/30 hover:border-ink/20 transition-colors duration-150 focus-visible:ring-2"
          >
            <RefreshCw size={13} aria-hidden="true" /> Retry
          </button>
        </div>
      </div>
    );
  }

  const isEmpty = !messages.length && !streaming;
  const sendDisabled = !connected || !input.trim() || !!streaming;

  return (
    <div className="flex flex-col h-screen">
      <PageHeader
        eyebrow="RAG"
        title="Ask your procurement data"
        action={
          <span className="flex items-center gap-1.5 text-xs text-ink/40">
            <span
              className={`inline-flex h-2 w-2 rounded-full ${connected ? "bg-matched" : "bg-critical animate-pulse"}`}
              aria-hidden="true"
            />
            {connected ? "Ready" : "Reconnecting…"}
          </span>
        }
      />

      <div
        className="flex-1 overflow-y-auto p-6"
        aria-live="polite"
        aria-label="Chat messages"
      >
        {/* ── Empty state ────────────────────────────────────────────────── */}
        {isEmpty && (
          <div className="max-w-2xl mx-auto mt-8">
            <div className="flex flex-col items-center text-center mb-8">
              <div className="w-12 h-12 rounded-full bg-ledger/10 flex items-center justify-center mb-3">
                <MessagesSquare size={22} className="text-ledgerLight" strokeWidth={1.5} aria-hidden="true" />
              </div>
              <div className="font-display text-xl text-ink mb-1">Ask your documents</div>
              <div className="text-sm text-ink/50">
                Query contracts, invoices, and vendor data in plain language.
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {SUGGESTED.map((s) => (
                <button
                  key={s}
                  onClick={() => submitSuggestion(s)}
                  disabled={!connected}
                  className="text-left px-4 py-3 border border-line rounded-lg bg-white text-sm text-ink/70
                             hover:border-ledgerLight hover:bg-ledgerLight/5 hover:text-ink transition-colors duration-150
                             disabled:opacity-40 disabled:cursor-not-allowed focus-visible:ring-2"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Messages ────────────────────────────────────────────────────── */}
        {!isEmpty && (
          <div className="max-w-3xl mx-auto space-y-5">
            <AnimatePresence initial={false}>
              {messages.map((m, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <MessageBubble message={m} />
                </motion.div>
              ))}
            </AnimatePresence>

            {streaming && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.1 }}
              >
                <MessageBubble message={{ role: "assistant", content: streaming }} pending />
              </motion.div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* ── Input bar ─────────────────────────────────────────────────────── */}
      <div className="border-t border-line bg-white px-6 py-4">
        <form
          onSubmit={submit}
          className="max-w-3xl mx-auto flex gap-2"
          aria-label="Chat input"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={connected ? "Ask a question about your procurement documents…" : "Reconnecting…"}
            disabled={!connected}
            aria-label="Message input"
            className="flex-1 border border-line rounded-lg px-4 py-2.5 text-sm outline-none
                       focus:border-ledgerLight bg-paper/60
                       disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={sendDisabled}
            aria-label="Send message"
            className="px-4 py-2.5 rounded-lg bg-ledger text-paper text-sm flex items-center gap-2
                       hover:bg-ledgerLight transition-colors duration-150
                       disabled:opacity-40 disabled:cursor-not-allowed
                       focus-visible:ring-2 focus-visible:ring-ledgerLight"
          >
            {streaming ? (
              <Loader2 size={15} className="animate-spin" aria-hidden="true" />
            ) : (
              <Send size={15} aria-hidden="true" />
            )}
            Send
          </button>
        </form>
      </div>
    </div>
  );
}

function MessageBubble({ message, pending }) {
  const isUser = message.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={clsx(
          "rounded-xl px-4 py-3 text-sm max-w-[520px]",
          isUser
            ? "bg-ledger text-paper"
            : "bg-white border border-line"
        )}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap leading-relaxed">{message.content}</div>
        ) : (
          <div className="prose prose-sm max-w-none leading-relaxed
            prose-p:my-1 prose-p:leading-relaxed
            prose-ul:my-1 prose-ul:pl-4 prose-li:my-0.5
            prose-ol:my-1 prose-ol:pl-4
            prose-strong:font-semibold prose-strong:text-ink
            prose-h1:text-base prose-h1:font-semibold prose-h1:my-2
            prose-h2:text-sm prose-h2:font-semibold prose-h2:my-1.5
            prose-h3:text-sm prose-h3:font-semibold prose-h3:my-1
            prose-code:text-xs prose-code:bg-paper prose-code:px-1 prose-code:rounded
            prose-pre:bg-paper prose-pre:text-xs prose-pre:p-2 prose-pre:rounded
            [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
            <ReactMarkdown>{message.content}</ReactMarkdown>
            {pending && (
              <span className="animate-pulse" aria-label="Typing">▍</span>
            )}
          </div>
        )}
        {!!message.citations?.length && (
          <div className="flex flex-wrap gap-1.5 mt-2.5 pt-2.5 border-t border-line/60">
            {message.citations.map((c, i) => (
              <span
                key={i}
                title={c.title}
                className="inline-flex items-center gap-1 text-[11px] bg-paper px-2 py-0.5 rounded border border-line text-ink/50"
              >
                <FileText size={10} aria-hidden="true" />
                {c.title?.slice(0, 30) || `Source ${i + 1}`}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


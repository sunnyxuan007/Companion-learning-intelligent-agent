"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, MessageSquare, Send, X } from "lucide-react";

const ANIM_MS = 220;

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface VolunteerChatDrawerProps {
  open: boolean;
  onClose: () => void;
  context?: Record<string, unknown>;
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-blue-600 text-white"
            : "border bg-white text-gray-800"
        }`}
      >
        {msg.content}
      </div>
    </div>
  );
}

export default function VolunteerChatDrawer({ open, onClose, context }: VolunteerChatDrawerProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  // Welcome message when drawer first opens
  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([
        { role: "assistant", content: "你好！我是志愿填报助手，有什么可以帮你的吗？你可以问我关于院校、专业、录取策略的问题。" },
      ]);
    }
  }, [open, messages.length]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const res = await fetch("/api/v1/volunteer/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          context: context || undefined,
        }),
      });
      if (!res.ok) throw new Error("请求失败");
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "抱歉，我暂时无法回答，请稍后再试。" }]);
    }
    setLoading(false);
  }, [input, loading, sessionId, context]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // Reset when context changes (user clicked a different college)
  useEffect(() => {
    if (context?.college_name) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `已切换到院校: ${context.college_name}，有什么想了解的吗？`,
        },
      ]);
    }
  }, [context?.college_name]);

  return (
    <div
      className={`fixed right-0 top-0 z-[30] flex h-full w-[min(440px,92vw)] flex-col border-l bg-gray-50 shadow-xl transition-transform duration-[220ms] ease-out ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
      style={{ willChange: "transform" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b bg-white px-4 py-3">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-blue-600" />
          <span className="font-semibold text-gray-900">志愿填报助手</span>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Messages */}
      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl border bg-white px-4 py-2.5 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              思考中...
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t bg-white p-3">
        <div className="flex items-end gap-2 rounded-xl border bg-gray-50 p-2 focus-within:border-blue-400 focus-within:ring-1 focus-within:ring-blue-400">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题..."
            rows={1}
            className="max-h-32 min-h-[36px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || loading}
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-1 text-[11px] text-gray-400">Enter 发送 · Shift+Enter 换行</p>
      </div>
    </div>
  );
}

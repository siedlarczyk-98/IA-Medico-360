import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { ModeChip } from './ModeChip';
import type { Message } from '../api/orquestrador';
import { useIsMobile } from '../hooks/useIsMobile';

const DISCLAIMER = '⚕️ Suporte à decisão clínica. A conduta é de responsabilidade exclusiva do médico assistente.';

interface Props {
  messages: Message[];
  streaming?: boolean;
  scrollToBottomTrigger?: number;
}

export function ChatView({ messages, streaming, scrollToBottomTrigger }: Props) {
  const isMobile = useIsMobile();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Só rola quando o usuário envia uma nova mensagem (scrollToBottomTrigger muda)
  useEffect(() => {
    if (scrollToBottomTrigger !== undefined && scrollToBottomTrigger > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [scrollToBottomTrigger]);

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: isMobile ? '16px 20px 0' : '24px 40px 0', display: 'flex', justifyContent: 'center' }}>
      <div style={{ width: 720, maxWidth: '100%', paddingBottom: 16 }}>
        {messages.map((msg, i) => (
          msg.role === 'user'
            ? <UserMessage key={i} content={msg.content} />
            : <AssistantMessage key={i} content={msg.content} mode={msg.mode} confidence={msg.confidence} />
        ))}
        {streaming && <ThinkingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 18 }}>
      <div style={{
        maxWidth: 480, background: 'var(--ink)', color: '#fff',
        padding: '11px 14px', borderRadius: 14, borderBottomRightRadius: 4,
        fontSize: 13, lineHeight: 1.5,
      }}>{content}</div>
    </div>
  );
}

function AssistantMessage({ content, mode, confidence }: { content: string; mode?: string; confidence?: number }) {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 24 }}>
      <AssistantAvatar />
      <div style={{ flex: 1, minWidth: 0, paddingTop: 4 }}>
        {mode && (
          <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            {['raciocinio','farmaco','busca','produtividade'].includes(mode)
              ? <ModeChip mode={mode} confidence={confidence} />
              : <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '4px 10px', fontSize: 11, fontWeight: 600,
                  color: 'var(--petrol)', background: 'var(--fill2)',
                  border: '1px solid var(--line2)', borderRadius: 999,
                }}>{mode}</span>
            }
          </div>
        )}
        <div style={{ fontSize: 13, color: 'var(--ink)', lineHeight: 1.55, wordBreak: 'break-word' }}>
          <ReactMarkdown
            components={{
              p: ({ children }) => <p style={{ margin: '0 0 8px' }}>{children}</p>,
              strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
              em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
              ul: ({ children }) => <ul style={{ margin: '4px 0 8px', paddingLeft: 20 }}>{children}</ul>,
              ol: ({ children }) => <ol style={{ margin: '4px 0 8px', paddingLeft: 20 }}>{children}</ol>,
              li: ({ children }) => <li style={{ marginBottom: 2 }}>{children}</li>,
              h1: ({ children }) => <h1 style={{ fontSize: 15, fontWeight: 700, margin: '12px 0 6px' }}>{children}</h1>,
              h2: ({ children }) => <h2 style={{ fontSize: 14, fontWeight: 700, margin: '10px 0 4px' }}>{children}</h2>,
              h3: ({ children }) => <h3 style={{ fontSize: 13, fontWeight: 600, margin: '8px 0 4px' }}>{children}</h3>,
              code: ({ children, className }) =>
                className
                  ? <code style={{ display: 'block', background: 'var(--fill2)', border: '1px solid var(--line2)', borderRadius: 6, padding: '8px 12px', fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap', margin: '4px 0' }}>{children}</code>
                  : <code style={{ background: 'var(--fill2)', border: '1px solid var(--line2)', borderRadius: 4, padding: '1px 5px', fontSize: 12, fontFamily: 'monospace' }}>{children}</code>,
              pre: ({ children }) => <>{children}</>,
              blockquote: ({ children }) => <blockquote style={{ borderLeft: '3px solid var(--line2)', paddingLeft: 12, margin: '4px 0', color: 'var(--pen2)' }}>{children}</blockquote>,
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
        <div style={{
          marginTop: 14, fontSize: 11, color: 'var(--pen3)',
          borderTop: '1px solid var(--line2)', paddingTop: 10,
          display: 'flex', justifyContent: 'space-between', gap: 14, alignItems: 'center',
        }}>
          <span style={{ flex: 1 }}>{DISCLAIMER}</span>
          <div style={{ display: 'flex', gap: 6 }}>
            {['↻', '↗', '♥'].map(icon => (
              <button key={icon} style={{
                width: 24, height: 24, borderRadius: 6, border: '1px solid var(--line2)',
                background: '#fff', fontSize: 11, color: 'var(--pen2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>{icon}</button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <AssistantAvatar />
      <div style={{ paddingTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{
            width: 5, height: 5, borderRadius: '50%', background: 'var(--green)',
            animation: 'pulse 1.2s ease-in-out infinite',
            animationDelay: `${i * 0.2}s`,
          }} />
        ))}
        <span style={{ fontSize: 12, color: 'var(--pen2)', fontWeight: 500 }}>
          Roteando para o modo mais adequado…
        </span>
      </div>
    </div>
  );
}

function AssistantAvatar() {
  return (
    <div style={{
      width: 30, height: 30, borderRadius: 8, background: 'var(--mint)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    }}>
      <svg width="14" height="14" viewBox="0 0 32 32" fill="none">
        <path d="M3 26 L3 10 Q3 5 8 5 Q12 5 13 9 L16 22 L19 9 Q20 5 24 5 Q29 5 29 10 L29 26"
              stroke="#014751" strokeWidth="3.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="8" cy="13" r="1.6" fill="#00d17d" />
      </svg>
    </div>
  );
}

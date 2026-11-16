// Talk to the assistant. Streams tokens; tool calls show as a quiet status line.
import { ComponentRef, useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Button, Field } from '@/components/ui';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { api, streamChat, Thread, ThreadMessage } from '@/lib/api';

type Msg = { id: string; role: 'user' | 'assistant'; text: string; status?: string };

export default function ChatScreen() {
  const theme = useTheme();
  const [threadId, setThreadId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);

  // Resume the most recent thread on open.
  useEffect(() => {
    (async () => {
      try {
        const threads = await api<Thread[]>('/api/chat/threads');
        if (threads[0]) {
          const t = await api<Thread & { messages: ThreadMessage[] }>(`/api/chat/threads/${threads[0].id}`);
          setThreadId(t.id);
          setMessages(t.messages.map((m) => ({ id: String(m.id), role: m.role, text: m.text })));
        }
      } catch {
        /* shown on first send instead */
      }
    })();
  }, []);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setBusy(true);
    const assistantId = `a${Date.now()}`;
    setMessages((m) => [...m, { id: `u${Date.now()}`, role: 'user', text }, { id: assistantId, role: 'assistant', text: '', status: 'Thinking…' }]);
    const patch = (fn: (m: Msg) => Msg) => setMessages((all) => all.map((m) => (m.id === assistantId ? fn(m) : m)));
    try {
      await streamChat(text, threadId, (ev) => {
        if (ev.type === 'thread') setThreadId(ev.thread_id);
        else if (ev.type === 'text') patch((m) => ({ ...m, text: m.text + ev.text, status: undefined }));
        else if (ev.type === 'tool') patch((m) => ({ ...m, status: `Using ${ev.name.replace(/_/g, ' ')}…` }));
        else if (ev.type === 'error') patch((m) => ({ ...m, text: m.text || `⚠︎ ${ev.message}`, status: undefined }));
        else if (ev.type === 'done') patch((m) => ({ ...m, status: undefined }));
      });
    } catch (e) {
      patch((m) => ({ ...m, text: m.text || `⚠︎ ${e instanceof Error ? e.message : String(e)}`, status: undefined }));
    } finally {
      setBusy(false);
    }
  };

  const newThread = () => {
    setThreadId(null);
    setMessages([]);
  };

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safe} edges={['top']}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.safe} keyboardVerticalOffset={BottomTabInset}>
          <View style={styles.header}>
            <ThemedText type="subtitle">Assistant</ThemedText>
            <Button title="New chat" kind="secondary" onPress={newThread} disabled={busy} />
          </View>
          <ScrollView ref={scroll} contentContainerStyle={styles.list} onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: true })}>
            {messages.length === 0 ? (
              <ThemedText type="small" themeColor="textSecondary" style={styles.hint}>
                Try: “weighed 84.2 kg this morning”, “what did my last lipid panel say?”, “plan my meals for a 150 g protein day”.
              </ThemedText>
            ) : null}
            {messages.map((m) => (
              <View
                key={m.id}
                style={[styles.bubble, m.role === 'user' ? [styles.user, { backgroundColor: '#2f7cf6' }] : { backgroundColor: theme.backgroundElement }]}>
                {m.text ? <ThemedText style={m.role === 'user' ? { color: '#fff' } : undefined}>{m.text}</ThemedText> : null}
                {m.status ? <ThemedText type="small" themeColor="textSecondary">{m.status}</ThemedText> : null}
              </View>
            ))}
          </ScrollView>
          <View style={styles.composer}>
            <Field
              value={input}
              onChangeText={setInput}
              placeholder="Message your assistant"
              multiline
              onSubmitEditing={send}
              blurOnSubmit={false}
              returnKeyType="send"
            />
            <Button title="Send" onPress={send} busy={busy} disabled={!input.trim()} />
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center' },
  safe: { flex: 1, width: '100%', maxWidth: MaxContentWidth },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: Spacing.three, paddingTop: Spacing.six, paddingBottom: Spacing.two },
  list: { padding: Spacing.three, gap: Spacing.two, flexGrow: 1 },
  hint: { marginTop: Spacing.four },
  bubble: { padding: Spacing.three, borderRadius: Spacing.three, maxWidth: '92%', alignSelf: 'flex-start' },
  user: { alignSelf: 'flex-end' },
  composer: { flexDirection: 'row', gap: Spacing.two, padding: Spacing.three, paddingBottom: BottomTabInset + Spacing.three, alignItems: 'flex-end' },
});

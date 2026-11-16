// Today: what the assistant wants you to see, plus your latest numbers.
import { Link } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
import { Button, Card, Empty, Pill, Section } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { api, fmtNum, fmtWhen, Insight, Observation } from '@/lib/api';

const KIND_LABELS: Record<string, string> = {
  weight: 'Weight', bp_systolic: 'Systolic', bp_diastolic: 'Diastolic', heart_rate: 'Heart rate',
  resting_heart_rate: 'Resting HR', steps: 'Steps', sleep_hours: 'Sleep', glucose: 'Glucose',
  spo2: 'SpO₂', hrv_sdnn: 'HRV', active_energy: 'Active kcal', vo2_max: 'VO₂ max',
};

export default function TodayScreen() {
  const [insights, setInsights] = useState<Insight[] | null>(null);
  const [latest, setLatest] = useState<Observation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [i, l] = await Promise.all([api<Insight[]>('/api/insights'), api<Observation[]>('/api/observations/latest')]);
      setInsights(i);
      setLatest(l);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setBusy(true);
    await load();
  }, [load]);

  useEffect(() => {
    void (async () => {
      await load();
    })();
  }, [load]);

  const dismiss = async (id: number) => {
    setInsights((cur) => cur?.filter((x) => x.id !== id) ?? null);
    try {
      await api(`/api/insights/${id}/dismiss`, { method: 'POST' });
    } catch {
      load();
    }
  };

  const runBriefing = async () => {
    setBusy(true);
    try {
      await api('/api/insights/run', { method: 'POST' });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  const shown = latest.filter((o) => KIND_LABELS[o.kind]).slice(0, 8);

  return (
    <Screen title="Today" refreshing={busy} onRefresh={refresh}>
      {error ? (
        <Card>
          <ThemedText type="smallBold">Can’t reach the API</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">{error}</ThemedText>
          <Link href="/settings" asChild>
            <Pressable><ThemedText type="linkPrimary">Check server URL and token →</ThemedText></Pressable>
          </Link>
        </Card>
      ) : null}

      <Section title="From your assistant" action={<Button title="Refresh briefing" kind="secondary" onPress={runBriefing} busy={busy} />}>
        {insights === null ? <Empty text="Loading…" /> : insights.length === 0 ? (
          <Empty text="Nothing yet. Log a few things or import Apple Health, then refresh the briefing." />
        ) : (
          insights.map((ins) => (
            <Card key={ins.id}>
              <View style={styles.cardHead}>
                <Pill text={ins.kind} tone={ins.severity === 'urgent' ? 'bad' : ins.severity === 'attention' ? 'warn' : 'neutral'} />
                <Pressable onPress={() => dismiss(ins.id)} hitSlop={8}>
                  <ThemedText type="small" themeColor="textSecondary">Dismiss</ThemedText>
                </Pressable>
              </View>
              <ThemedText type="smallBold">{ins.title}</ThemedText>
              <ThemedText type="small">{ins.body}</ThemedText>
              {ins.due_at ? <ThemedText type="small" themeColor="textSecondary">Due {fmtWhen(ins.due_at)}</ThemedText> : null}
            </Card>
          ))
        )}
      </Section>

      <Section title="Latest readings">
        {shown.length === 0 ? <Empty text="No readings yet." /> : (
          <View style={styles.grid}>
            {shown.map((o) => (
              <Card key={o.kind} style={styles.tile}>
                <ThemedText type="small" themeColor="textSecondary">{KIND_LABELS[o.kind]}</ThemedText>
                <ThemedText style={styles.value}>
                  {fmtNum(o.value)} <ThemedText type="small" themeColor="textSecondary">{o.unit}</ThemedText>
                </ThemedText>
                <ThemedText type="small" themeColor="textSecondary">{fmtWhen(o.observed_at)}</ThemedText>
              </Card>
            ))}
          </View>
        )}
      </Section>
    </Screen>
  );
}

const styles = StyleSheet.create({
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.two },
  tile: { minWidth: 150, flexGrow: 1, flexBasis: '45%' },
  value: { fontSize: 24, fontWeight: 600, lineHeight: 30 },
});

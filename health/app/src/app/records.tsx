// Medical records: upload documents (labs, visit notes), medications, conditions.
import * as DocumentPicker from 'expo-document-picker';
import { useCallback, useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
import { Button, Card, Empty, Field, Pill, Row, Section } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { api, Doc, fmtWhen, Medication, upload } from '@/lib/api';

type Condition = { id: number; name: string; status: string; onset_date: string | null };

export default function RecordsScreen() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [meds, setMeds] = useState<Medication[]>([]);
  const [conds, setConds] = useState<Condition[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [newMed, setNewMed] = useState({ name: '', dose: '', frequency: '' });
  const [newCond, setNewCond] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, m, c] = await Promise.all([api<Doc[]>('/api/documents'), api<Medication[]>('/api/medications'), api<Condition[]>('/api/conditions')]);
      setDocs(d); setMeds(m); setConds(c); setMsg(null);
    } catch (e) {
      setMsg(`⚠︎ ${e instanceof Error ? e.message : String(e)}`);
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

  // Poll while something is still being extracted.
  useEffect(() => {
    if (!docs.some((d) => d.status === 'pending' || d.status === 'processing')) return;
    const t = setTimeout(load, 4000);
    return () => clearTimeout(t);
  }, [docs, load]);

  const pick = async () => {
    const res = await DocumentPicker.getDocumentAsync({ type: ['application/pdf', 'image/*', 'text/plain'], multiple: true, copyToCacheDirectory: true });
    if (res.canceled) return;
    setBusy(true);
    try {
      for (const a of res.assets) {
        const file = Platform.OS === 'web' && a.file ? a.file : { uri: a.uri, name: a.name, type: a.mimeType ?? 'application/octet-stream' };
        await upload('/api/documents', file);
      }
      setMsg(`Uploaded ${res.assets.length} file(s). Extraction runs in the background.`);
      await load();
    } catch (e) {
      setMsg(`⚠︎ ${e instanceof Error ? e.message : String(e)}`);
      setBusy(false);
    }
  };

  const addMed = async () => {
    await api('/api/medications', { method: 'POST', json: { name: newMed.name, dose: newMed.dose || null, frequency: newMed.frequency || null } });
    setNewMed({ name: '', dose: '', frequency: '' });
    load();
  };

  const takeMed = async (id: number) => {
    await api(`/api/medications/${id}/log`, { method: 'POST', json: {} });
    load();
  };

  const addCond = async () => {
    await api('/api/conditions', { method: 'POST', json: { name: newCond } });
    setNewCond('');
    load();
  };

  return (
    <Screen title="Records" refreshing={busy} onRefresh={refresh}>
      {msg ? <ThemedText type="small" themeColor="textSecondary">{msg}</ThemedText> : null}

      <Section title="Documents" action={<Button title="Upload" kind="secondary" onPress={pick} busy={busy} />}>
        {docs.length === 0 ? <Empty text="Upload lab reports, visit notes, imaging reports. They get read and filed automatically." /> : null}
        {docs.map((d) => (
          <Pressable key={d.id} onPress={() => setOpen(open === d.id ? null : d.id)}>
            <Card>
              <View style={styles.head}>
                <ThemedText type="smallBold" style={{ flex: 1 }} numberOfLines={1}>{d.filename}</ThemedText>
                <Pill text={d.status} tone={d.status === 'failed' ? 'bad' : d.status === 'processed' ? 'good' : 'warn'} />
              </View>
              <ThemedText type="small" themeColor="textSecondary">
                {[d.kind?.replace('_', ' '), d.provider_name, d.document_date ?? fmtWhen(d.uploaded_at)].filter(Boolean).join(' · ')}
              </ThemedText>
              {open === d.id && d.summary ? <ThemedText type="small">{d.summary}</ThemedText> : null}
              {open === d.id && d.error ? <ThemedText type="small">{d.error}</ThemedText> : null}
            </Card>
          </Pressable>
        ))}
      </Section>

      <Section title="Medications">
        {meds.length === 0 ? <Empty text="No active medications." /> : null}
        {meds.map((m) => (
          <Card key={m.id}>
            <View style={styles.head}>
              <View style={{ flex: 1 }}>
                <ThemedText type="smallBold">{m.name}{m.dose ? ` · ${m.dose}` : ''}</ThemedText>
                <ThemedText type="small" themeColor="textSecondary">
                  {[m.frequency, m.reason].filter(Boolean).join(' · ')}{m.last_taken_at ? ` · last ${fmtWhen(m.last_taken_at)}` : ''}
                </ThemedText>
              </View>
              <Button title="Taken" kind="secondary" onPress={() => takeMed(m.id)} />
            </View>
          </Card>
        ))}
        <Card>
          <Row>
            <Field label="Add medication" value={newMed.name} onChangeText={(v) => setNewMed({ ...newMed, name: v })} placeholder="Name" />
            <Field label="Dose" value={newMed.dose} onChangeText={(v) => setNewMed({ ...newMed, dose: v })} placeholder="10 mg" />
          </Row>
          <Row>
            <Field label="Frequency" value={newMed.frequency} onChangeText={(v) => setNewMed({ ...newMed, frequency: v })} placeholder="once daily" />
            <Button title="Add" onPress={addMed} disabled={!newMed.name.trim()} />
          </Row>
        </Card>
      </Section>

      <Section title="Conditions">
        {conds.length === 0 ? <Empty text="Nothing recorded." /> : null}
        {conds.map((c) => (
          <Card key={c.id}>
            <View style={styles.head}>
              <ThemedText type="smallBold">{c.name}</ThemedText>
              <Pill text={c.status} />
            </View>
          </Card>
        ))}
        <Card>
          <Row>
            <Field label="Add condition" value={newCond} onChangeText={setNewCond} placeholder="e.g. Hypertension" />
            <Button title="Add" onPress={addCond} disabled={!newCond.trim()} />
          </Row>
        </Card>
      </Section>
    </Screen>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
});

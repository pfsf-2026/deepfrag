// Server connection and profile basics.
import * as DocumentPicker from 'expo-document-picker';
import { useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
import { Button, Card, Field, Row, Section } from '@/components/ui';
import { api, getConfig, saveConfig, upload } from '@/lib/api';

type Profile = { birth_date: string | null; sex: string | null; height_cm: string | null; timezone: string; display_name: string | null };

export default function SettingsScreen() {
  const [baseUrl, setBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [profile, setProfile] = useState<Partial<Profile>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getConfig().then((c) => { setBaseUrl(c.baseUrl); setToken(c.token); });
    api<Profile>('/api/profile').then(setProfile).catch(() => {});
  }, []);

  const test = async () => {
    setBusy(true);
    try {
      await saveConfig(baseUrl, token);
      const r = await api<{ status: string; model: string }>('/healthz');
      await api('/api/profile');
      setStatus(`Connected. Model: ${r.model}`);
    } catch (e) {
      setStatus(`⚠︎ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const saveProfile = async () => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = {};
      if (profile.birth_date) body.birth_date = profile.birth_date;
      if (profile.sex) body.sex = profile.sex;
      if (profile.height_cm) body.height_cm = parseFloat(String(profile.height_cm));
      if (profile.timezone) body.timezone = profile.timezone;
      setProfile(await api<Profile>('/api/profile', { method: 'PUT', json: body }));
      setStatus('Profile saved.');
    } catch (e) {
      setStatus(`⚠︎ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const importApple = async () => {
    const res = await DocumentPicker.getDocumentAsync({ type: ['application/zip', 'text/xml', 'application/xml', '*/*'], copyToCacheDirectory: true });
    if (res.canceled) return;
    setBusy(true);
    try {
      const a = res.assets[0];
      const file = Platform.OS === 'web' && a.file ? a.file : { uri: a.uri, name: a.name, type: a.mimeType ?? 'application/zip' };
      const r = await upload<{ written: { observations: number; workouts: number } }>('/api/import/apple-health', file);
      setStatus(`Imported ${r.written.observations} readings and ${r.written.workouts} workouts.`);
    } catch (e) {
      setStatus(`⚠︎ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen title="Settings">
      {status ? <ThemedText type="small" themeColor="textSecondary">{status}</ThemedText> : null}
      <Section title="Server">
        <Card>
          <Field label="API URL" value={baseUrl} onChangeText={setBaseUrl} autoCapitalize="none" autoCorrect={false} placeholder="http://localhost:8000" />
          <Field label="App token" value={token} onChangeText={setToken} autoCapitalize="none" autoCorrect={false} secureTextEntry placeholder="HEALTH_APP_TOKEN" />
          <Button title="Save and test" onPress={test} busy={busy} />
        </Card>
      </Section>
      <Section title="Profile">
        <Card>
          <Row>
            <Field label="Birth date" value={profile.birth_date ?? ''} onChangeText={(v) => setProfile({ ...profile, birth_date: v })} placeholder="1985-06-01" />
            <Field label="Sex" value={profile.sex ?? ''} onChangeText={(v) => setProfile({ ...profile, sex: v })} placeholder="male / female / other" autoCapitalize="none" />
          </Row>
          <Row>
            <Field label="Height cm" value={profile.height_cm ? String(profile.height_cm) : ''} onChangeText={(v) => setProfile({ ...profile, height_cm: v })} keyboardType="decimal-pad" placeholder="180" />
            <Field label="Timezone" value={profile.timezone ?? ''} onChangeText={(v) => setProfile({ ...profile, timezone: v })} placeholder="America/New_York" autoCapitalize="none" />
          </Row>
          <Button title="Save profile" onPress={saveProfile} busy={busy} />
        </Card>
      </Section>
      <Section title="Import">
        <Card>
          <ThemedText type="small" themeColor="textSecondary">
            iPhone Health app → your picture → Export All Health Data. Pick the export.zip here.
          </ThemedText>
          <Button title="Import Apple Health export" kind="secondary" onPress={importApple} busy={busy} />
        </Card>
      </Section>
    </Screen>
  );
}

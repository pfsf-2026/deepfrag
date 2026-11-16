// Quick manual entry: a measurement, a meal, a workout. The assistant can also
// log all of these from chat; this is for when typing a number is faster.
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
import { Button, Card, Field, Row, Section } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { api } from '@/lib/api';

const QUICK_KINDS = [
  { kind: 'weight', label: 'Weight', unit: 'kg' },
  { kind: 'bp', label: 'Blood pressure', unit: 'mmHg' },
  { kind: 'glucose', label: 'Glucose', unit: 'mg/dL' },
  { kind: 'heart_rate', label: 'Heart rate', unit: 'bpm' },
  { kind: 'sleep_hours', label: 'Sleep', unit: 'h' },
  { kind: 'water_ml', label: 'Water', unit: 'mL' },
  { kind: 'mood', label: 'Mood 1-5', unit: 'score' },
];

export default function LogScreen() {
  const [kind, setKind] = useState(QUICK_KINDS[0]);
  const [value, setValue] = useState('');
  const [value2, setValue2] = useState('');
  const [unit, setUnit] = useState(QUICK_KINDS[0].unit);
  const [meal, setMeal] = useState('');
  const [kcal, setKcal] = useState('');
  const [protein, setProtein] = useState('');
  const [wkind, setWkind] = useState('run');
  const [minutes, setMinutes] = useState('');
  const [km, setKm] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg(`${label} saved.`);
    } catch (e) {
      setMsg(`⚠︎ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const saveMeasurement = () =>
    run('Measurement', async () => {
      if (kind.kind === 'bp') {
        await api('/api/observations', { method: 'POST', json: { kind: 'bp_systolic', value: parseFloat(value), unit: 'mmHg' } });
        await api('/api/observations', { method: 'POST', json: { kind: 'bp_diastolic', value: parseFloat(value2), unit: 'mmHg' } });
      } else {
        await api('/api/observations', { method: 'POST', json: { kind: kind.kind, value: parseFloat(value), unit } });
      }
      setValue('');
      setValue2('');
    });

  const saveMeal = () =>
    run('Meal', async () => {
      await api('/api/meals', {
        method: 'POST',
        json: { description: meal, calories: kcal ? parseFloat(kcal) : null, protein_g: protein ? parseFloat(protein) : null },
      });
      setMeal(''); setKcal(''); setProtein('');
    });

  const saveWorkout = () =>
    run('Workout', async () => {
      await api('/api/workouts', {
        method: 'POST',
        json: { kind: wkind, duration_min: minutes ? parseFloat(minutes) : null, distance_km: km ? parseFloat(km) : null },
      });
      setMinutes(''); setKm('');
    });

  return (
    <Screen title="Log">
      {msg ? <ThemedText type="small" themeColor="textSecondary">{msg}</ThemedText> : null}

      <Section title="Measurement">
        <Card>
          <View style={styles.chips}>
            {QUICK_KINDS.map((k) => (
              <Button key={k.kind} title={k.label} kind={k.kind === kind.kind ? 'primary' : 'secondary'} onPress={() => { setKind(k); setUnit(k.unit); }} />
            ))}
          </View>
          <Row>
            <Field label={kind.kind === 'bp' ? 'Systolic' : 'Value'} value={value} onChangeText={setValue} keyboardType="decimal-pad" placeholder="0" />
            {kind.kind === 'bp' ? (
              <Field label="Diastolic" value={value2} onChangeText={setValue2} keyboardType="decimal-pad" placeholder="0" />
            ) : (
              <Field label="Unit" value={unit} onChangeText={setUnit} placeholder={kind.unit} autoCapitalize="none" />
            )}
          </Row>
          <Button title="Save measurement" onPress={saveMeasurement} busy={busy} disabled={!value || (kind.kind === 'bp' && !value2)} />
        </Card>
      </Section>

      <Section title="Meal">
        <Card>
          <Field label="What did you eat?" value={meal} onChangeText={setMeal} placeholder="2 eggs, toast, coffee" multiline />
          <Row>
            <Field label="kcal (optional)" value={kcal} onChangeText={setKcal} keyboardType="decimal-pad" placeholder="—" />
            <Field label="Protein g (optional)" value={protein} onChangeText={setProtein} keyboardType="decimal-pad" placeholder="—" />
          </Row>
          <ThemedText type="small" themeColor="textSecondary">Tip: tell the assistant instead and it estimates the macros for you.</ThemedText>
          <Button title="Save meal" onPress={saveMeal} busy={busy} disabled={!meal.trim()} />
        </Card>
      </Section>

      <Section title="Workout">
        <Card>
          <View style={styles.chips}>
            {['run', 'walk', 'cycle', 'strength', 'swim', 'hiit', 'yoga', 'other'].map((k) => (
              <Button key={k} title={k} kind={k === wkind ? 'primary' : 'secondary'} onPress={() => setWkind(k)} />
            ))}
          </View>
          <Row>
            <Field label="Minutes" value={minutes} onChangeText={setMinutes} keyboardType="decimal-pad" placeholder="30" />
            <Field label="Distance km" value={km} onChangeText={setKm} keyboardType="decimal-pad" placeholder="—" />
          </Row>
          <Button title="Save workout" onPress={saveWorkout} busy={busy} disabled={!minutes && !km} />
        </Card>
      </Section>
    </Screen>
  );
}

const styles = StyleSheet.create({
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.two },
});

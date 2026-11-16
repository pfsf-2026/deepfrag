// Small shared primitives on top of the template's themed components.
import { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, TextInputProps, View } from 'react-native';

import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

import { ThemedText } from './themed-text';
import { ThemedView } from './themed-view';

export function Card({ children, style }: { children: ReactNode; style?: object }) {
  return (
    <ThemedView type="backgroundElement" style={[styles.card, style]}>
      {children}
    </ThemedView>
  );
}

export function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <ThemedText type="smallBold" themeColor="textSecondary" style={styles.sectionTitle}>
          {title}
        </ThemedText>
        {action}
      </View>
      {children}
    </View>
  );
}

export function Button({
  title,
  onPress,
  kind = 'primary',
  disabled,
  busy,
}: {
  title: string;
  onPress: () => void;
  kind?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  busy?: boolean;
}) {
  const theme = useTheme();
  const bg = kind === 'primary' ? '#2f7cf6' : kind === 'danger' ? '#d64545' : theme.backgroundSelected;
  const fg = kind === 'secondary' ? theme.text : '#fff';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [styles.button, { backgroundColor: bg, opacity: pressed || disabled ? 0.7 : 1 }]}>
      {busy ? <ActivityIndicator color={fg} /> : <ThemedText style={{ color: fg, fontWeight: 600 }}>{title}</ThemedText>}
    </Pressable>
  );
}

export function Field(props: TextInputProps & { label?: string }) {
  const theme = useTheme();
  const { label, style, ...rest } = props;
  return (
    <View style={styles.field}>
      {label ? (
        <ThemedText type="small" themeColor="textSecondary">
          {label}
        </ThemedText>
      ) : null}
      <TextInput
        placeholderTextColor={theme.textSecondary}
        {...rest}
        style={[styles.input, { color: theme.text, backgroundColor: theme.background, borderColor: theme.backgroundSelected }, style]}
      />
    </View>
  );
}

export function Row({ children, style }: { children: ReactNode; style?: object }) {
  return <View style={[styles.row, style]}>{children}</View>;
}

export function Empty({ text }: { text: string }) {
  return (
    <ThemedText type="small" themeColor="textSecondary" style={{ paddingVertical: Spacing.two }}>
      {text}
    </ThemedText>
  );
}

export function Pill({ text, tone = 'neutral' }: { text: string; tone?: 'neutral' | 'warn' | 'bad' | 'good' }) {
  const bg = { neutral: '#8884', warn: '#e9a23b55', bad: '#d6454555', good: '#2fa36b55' }[tone];
  return (
    <View style={[styles.pill, { backgroundColor: bg }]}>
      <ThemedText type="small">{text}</ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: Spacing.three, padding: Spacing.three, gap: Spacing.two },
  section: { gap: Spacing.two, marginBottom: Spacing.four },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sectionTitle: { textTransform: 'uppercase', letterSpacing: 1 },
  button: {
    paddingVertical: Spacing.two + 2,
    paddingHorizontal: Spacing.three,
    borderRadius: Spacing.two + 2,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
  },
  field: { gap: Spacing.one, flex: 1 },
  input: { borderWidth: 1, borderRadius: Spacing.two, paddingHorizontal: Spacing.three, paddingVertical: Spacing.two + 2, fontSize: 16, minHeight: 44 },
  row: { flexDirection: 'row', gap: Spacing.two, alignItems: 'flex-end' },
  pill: { paddingHorizontal: Spacing.two, paddingVertical: 2, borderRadius: Spacing.two, alignSelf: 'flex-start' },
});

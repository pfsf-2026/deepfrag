import { NativeTabs } from 'expo-router/native-tabs';
import { useColorScheme } from 'react-native';

import { Colors } from '@/constants/theme';

const TABS: { name: string; label: string; sf: string; md: string }[] = [
  { name: 'index', label: 'Today', sf: 'sun.max', md: 'wb_sunny' },
  { name: 'log', label: 'Log', sf: 'plus.circle', md: 'add_circle' },
  { name: 'chat', label: 'Assistant', sf: 'bubble.left.and.bubble.right', md: 'chat' },
  { name: 'records', label: 'Records', sf: 'doc.text', md: 'description' },
  { name: 'settings', label: 'Settings', sf: 'gearshape', md: 'settings' },
];

export default function AppTabs() {
  const scheme = useColorScheme();
  const colors = Colors[scheme === 'dark' ? 'dark' : 'light'];

  return (
    <NativeTabs backgroundColor={colors.background} indicatorColor={colors.backgroundElement} labelStyle={{ selected: { color: colors.text } }}>
      {TABS.map((t) => (
        <NativeTabs.Trigger key={t.name} name={t.name}>
          <NativeTabs.Trigger.Label>{t.label}</NativeTabs.Trigger.Label>
          <NativeTabs.Trigger.Icon sf={t.sf as any} md={t.md as any} />
        </NativeTabs.Trigger>
      ))}
    </NativeTabs>
  );
}

// Small key/value store: localStorage on web, SecureStore on native.
import { Platform } from 'react-native';

let SecureStore: typeof import('expo-secure-store') | null = null;
if (Platform.OS !== 'web') {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  SecureStore = require('expo-secure-store');
}

export async function getItem(key: string): Promise<string | null> {
  try {
    if (Platform.OS === 'web') return globalThis.localStorage?.getItem(key) ?? null;
    return (await SecureStore!.getItemAsync(key)) ?? null;
  } catch {
    return null;
  }
}

export async function setItem(key: string, value: string): Promise<void> {
  try {
    if (Platform.OS === 'web') globalThis.localStorage?.setItem(key, value);
    else await SecureStore!.setItemAsync(key, value);
  } catch {
    /* storage unavailable (private mode etc.) - the app still works for the session */
  }
}

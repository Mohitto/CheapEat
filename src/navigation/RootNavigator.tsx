import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { BottomTabNavigator } from './BottomTabNavigator';
import { SzczegółyPrzepisuScreen } from '../screens/SzczegółyPrzepisuScreen';
import type { RootStackParamList } from './types';

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Tabs" component={BottomTabNavigator} />
        <Stack.Screen
          name="SzczegółyPrzepisu"
          component={SzczegółyPrzepisuScreen}
          options={{ headerShown: true, title: 'Przepis' }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

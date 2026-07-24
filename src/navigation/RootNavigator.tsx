import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { BottomTabNavigator } from './BottomTabNavigator';
import { RecipeDetailScreen } from '../screens/RecipeDetailScreen';
import type { RootStackParamList } from './types';

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Tabs"         component={BottomTabNavigator} />
      <Stack.Screen name="RecipeDetail" component={RecipeDetailScreen}
        options={{ headerShown: true, title: 'Szczegóły przepisu', headerTintColor: '#2ECC71' }}
      />
    </Stack.Navigator>
  );
}

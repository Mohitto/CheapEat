import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Text } from 'react-native';
import { FeedScreen } from '../screens/FeedScreen';
import { CartScreen } from '../screens/CartScreen';
import { PreferencesScreen } from '../screens/PreferencesScreen';
import type { TabParamList } from './types';

const Tab = createBottomTabNavigator<TabParamList>();

const icon = (emoji: string) => () => <Text style={{ fontSize: 20 }}>{emoji}</Text>;

export function BottomTabNavigator() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#2ECC71',
        tabBarInactiveTintColor: '#999',
        tabBarStyle: { backgroundColor: '#fff', borderTopColor: '#eee' },
      }}
    >
      <Tab.Screen name="Feed"        component={FeedScreen}        options={{ tabBarLabel: 'Przepisy',    tabBarIcon: icon('🍽') }} />
      <Tab.Screen name="Cart"        component={CartScreen}        options={{ tabBarLabel: 'Koszyk',      tabBarIcon: icon('🛒') }} />
      <Tab.Screen name="Preferences" component={PreferencesScreen} options={{ tabBarLabel: 'Preferencje', tabBarIcon: icon('⚙️') }} />
    </Tab.Navigator>
  );
}

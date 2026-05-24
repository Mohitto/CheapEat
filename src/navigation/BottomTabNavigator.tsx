import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { FeedScreen } from '../screens/FeedScreen';
import { PreferencjeScreen } from '../screens/PreferencjeScreen';
import { ListaZakupówScreen } from '../screens/ListaZakupówScreen';
import type { TabParamList } from './types';

const Tab = createBottomTabNavigator<TabParamList>();

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
      <Tab.Screen
        name="Feed"
        component={FeedScreen}
        options={{ title: 'Przepisy', tabBarLabel: 'Przepisy' }}
      />
      <Tab.Screen
        name="ListaZakupów"
        component={ListaZakupówScreen}
        options={{ title: 'Lista zakupów', tabBarLabel: 'Zakupy' }}
      />
      <Tab.Screen
        name="Preferencje"
        component={PreferencjeScreen}
        options={{ title: 'Preferencje', tabBarLabel: 'Preferencje' }}
      />
    </Tab.Navigator>
  );
}

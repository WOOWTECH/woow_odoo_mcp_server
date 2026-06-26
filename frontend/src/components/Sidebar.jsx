import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  Wrench,
  Link,
  KeyRound,
  ScrollText,
  Shield,
  Settings,
  LogOut,
} from 'lucide-react';
import { apiGet, clearToken } from '../api';

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/tools', label: 'Tools', icon: Wrench },
  { to: '/config', label: 'Connection', icon: Link },
  { to: '/tokens', label: 'Tokens', icon: KeyRound },
  { to: '/logs', label: 'Logs', icon: ScrollText },
  { to: '/permissions', label: 'Permissions', icon: Shield },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
  const navigate = useNavigate();

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet('/health'),
    staleTime: 30_000,
  });

  const appType = health?.app_type || 'MCP Admin';
  const appTitle = appType === 'n8n' ? 'n8n MCP Admin' : appType === 'odoo' ? 'Odoo MCP Admin' : 'MCP Admin';

  function handleLogout() {
    clearToken();
    navigate('/login');
  }

  return (
    <aside className="w-60 bg-gray-900 border-r border-gray-800 flex flex-col h-screen fixed left-0 top-0">
      <div className="p-5 border-b border-gray-800">
        <h1 className="text-lg font-bold text-gray-100 tracking-tight">{appTitle}</h1>
        {health?.namespace && (
          <p className="text-xs text-gray-500 mt-1 font-mono">{health.namespace}</p>
        )}
      </div>

      <nav className="flex-1 py-3 px-3 space-y-1 overflow-y-auto">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-brand-600/20 text-brand-400 border border-brand-600/30'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              }`
            }
          >
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="p-3 border-t border-gray-800">
        {health?.version && (
          <div className="px-3 py-1.5 mb-2 text-xs text-gray-600 font-mono">
            v{health.version}
          </div>
        )}
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-500 hover:text-red-400 hover:bg-gray-800 transition-colors w-full"
        >
          <LogOut size={18} />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
}

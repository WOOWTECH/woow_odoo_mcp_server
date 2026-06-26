import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Settings,
  Save,
  Loader2,
  CheckCircle2,
  XCircle,
  RotateCw,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  Play,
  Square,
  Server,
  Shield,
  Network,
} from 'lucide-react';
import { apiGet, apiPut, apiPost } from '../api';

function SectionCard({ title, icon: Icon, children }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <div className="flex items-center gap-2 mb-4">
        <Icon size={18} className="text-brand-400" />
        <h3 className="text-lg font-semibold text-gray-100">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function StatusBadge({ running }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
        running
          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
          : 'bg-gray-700/50 text-gray-400 border border-gray-600'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${running ? 'bg-emerald-400' : 'bg-gray-500'}`} />
      {running ? 'Running' : 'Stopped'}
    </span>
  );
}

function Alert({ type, message }) {
  const styles = {
    success: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
    error: 'bg-red-500/10 border-red-500/20 text-red-400',
  };
  return (
    <div className={`flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm border ${styles[type]}`}>
      {type === 'success' ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
      <span>{message}</span>
    </div>
  );
}

const inputClass =
  'w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 placeholder-gray-600 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition-colors font-mono text-sm';

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [mcpForm, setMcpForm] = useState({ command: '', args: [], port: 8000, env: {} });
  const [proxyForm, setProxyForm] = useState({ timeout: 86400, bearer_token: '' });
  const [passwordForm, setPasswordForm] = useState({ current: '', new_password: '' });
  const [newEnvKey, setNewEnvKey] = useState('');
  const [newEnvVal, setNewEnvVal] = useState('');
  const [newArg, setNewArg] = useState('');
  const [showBearerToken, setShowBearerToken] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiGet('/settings'),
  });

  const { data: mcpStatus } = useQuery({
    queryKey: ['mcpStatus'],
    queryFn: () => apiGet('/settings/mcp/status'),
    refetchInterval: 5000,
  });

  useEffect(() => {
    if (settings) {
      const mcp = settings.mcp_server || {};
      setMcpForm({
        command: mcp.command || '',
        args: mcp.args || [],
        port: mcp.port || 8000,
        env: mcp.env || {},
      });
      const proxy = settings.proxy || {};
      setProxyForm({
        timeout: proxy.timeout || 86400,
        bearer_token: proxy.bearer_token || '',
      });
    }
  }, [settings]);

  // --- Mutations ---

  const saveMcpMutation = useMutation({
    mutationFn: (data) => apiPut('/settings/mcp_server', data),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['mcpStatus'] });
      setFeedback({ type: 'success', message: res.message || 'MCP server config saved' });
    },
    onError: (err) => setFeedback({ type: 'error', message: err.message }),
  });

  const saveProxyMutation = useMutation({
    mutationFn: (data) => apiPut('/settings/proxy', data),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setFeedback({ type: 'success', message: res.message || 'Proxy config saved' });
    },
    onError: (err) => setFeedback({ type: 'error', message: err.message }),
  });

  const restartMutation = useMutation({
    mutationFn: () => apiPost('/settings/mcp/restart'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcpStatus'] });
      setFeedback({ type: 'success', message: 'MCP server restarted' });
    },
    onError: (err) => setFeedback({ type: 'error', message: err.message }),
  });

  const passwordMutation = useMutation({
    mutationFn: (data) => apiPut('/settings/admin_password', data),
    onSuccess: () => {
      setPasswordForm({ current: '', new_password: '' });
      setFeedback({ type: 'success', message: 'Admin password updated' });
    },
    onError: (err) => setFeedback({ type: 'error', message: err.message }),
  });

  // --- Env var helpers ---

  function addEnvVar() {
    if (newEnvKey.trim()) {
      setMcpForm((prev) => ({
        ...prev,
        env: { ...prev.env, [newEnvKey.trim()]: newEnvVal },
      }));
      setNewEnvKey('');
      setNewEnvVal('');
    }
  }

  function removeEnvVar(key) {
    setMcpForm((prev) => {
      const env = { ...prev.env };
      delete env[key];
      return { ...prev, env };
    });
  }

  function addArg() {
    if (newArg.trim()) {
      setMcpForm((prev) => ({ ...prev, args: [...prev.args, newArg.trim()] }));
      setNewArg('');
    }
  }

  function removeArg(index) {
    setMcpForm((prev) => ({
      ...prev,
      args: prev.args.filter((_, i) => i !== index),
    }));
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-gray-500" size={24} />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-100">Settings</h2>
        <p className="text-sm text-gray-500 mt-1">
          MCP server process, proxy, and admin configuration
        </p>
      </div>

      {feedback && (
        <div className="mb-4">
          <Alert type={feedback.type} message={feedback.message} />
        </div>
      )}

      <div className="space-y-6 max-w-2xl">
        {/* MCP Server Process */}
        <SectionCard title="MCP Server Process" icon={Server}>
          <div className="flex items-center justify-between mb-4">
            <StatusBadge running={mcpStatus?.running} />
            <div className="flex gap-2">
              <button
                onClick={() => restartMutation.mutate()}
                disabled={restartMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg transition-colors"
              >
                {restartMutation.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <RotateCw size={14} />
                )}
                Restart
              </button>
            </div>
          </div>

          {mcpStatus?.running && (
            <div className="text-xs text-gray-500 mb-4 font-mono">
              PID: {mcpStatus.pid} | Restarts: {mcpStatus.restart_count}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Command</label>
              <input
                type="text"
                value={mcpForm.command}
                onChange={(e) => setMcpForm((p) => ({ ...p, command: e.target.value }))}
                placeholder="odoo-mcp-server"
                className={inputClass}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Port</label>
              <input
                type="number"
                value={mcpForm.port}
                onChange={(e) => setMcpForm((p) => ({ ...p, port: parseInt(e.target.value) || 8000 }))}
                className={inputClass + ' max-w-[120px]'}
              />
            </div>

            {/* Args */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Arguments</label>
              <div className="space-y-1.5">
                {mcpForm.args.map((arg, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <code className="flex-1 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300">
                      {arg}
                    </code>
                    <button
                      onClick={() => removeArg(i)}
                      className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newArg}
                    onChange={(e) => setNewArg(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addArg())}
                    placeholder="--flag value"
                    className={inputClass + ' flex-1'}
                  />
                  <button
                    onClick={addArg}
                    disabled={!newArg.trim()}
                    className="p-2.5 bg-gray-800 hover:bg-gray-700 disabled:text-gray-600 text-gray-300 rounded-lg transition-colors"
                  >
                    <Plus size={16} />
                  </button>
                </div>
              </div>
            </div>

            {/* Env vars */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">
                Environment Variables
              </label>
              <div className="space-y-1.5">
                {Object.entries(mcpForm.env).map(([key, val]) => (
                  <div key={key} className="flex items-center gap-2">
                    <code className="px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-xs text-brand-400 min-w-[140px]">
                      {key}
                    </code>
                    <input
                      type="text"
                      value={val}
                      onChange={(e) =>
                        setMcpForm((p) => ({
                          ...p,
                          env: { ...p.env, [key]: e.target.value },
                        }))
                      }
                      className={inputClass + ' flex-1'}
                    />
                    <button
                      onClick={() => removeEnvVar(key)}
                      className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newEnvKey}
                    onChange={(e) => setNewEnvKey(e.target.value)}
                    placeholder="KEY"
                    className={inputClass + ' w-[140px]'}
                  />
                  <input
                    type="text"
                    value={newEnvVal}
                    onChange={(e) => setNewEnvVal(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addEnvVar())}
                    placeholder="value"
                    className={inputClass + ' flex-1'}
                  />
                  <button
                    onClick={addEnvVar}
                    disabled={!newEnvKey.trim()}
                    className="p-2.5 bg-gray-800 hover:bg-gray-700 disabled:text-gray-600 text-gray-300 rounded-lg transition-colors"
                  >
                    <Plus size={16} />
                  </button>
                </div>
              </div>
            </div>

            <button
              onClick={() => saveMcpMutation.mutate(mcpForm)}
              disabled={saveMcpMutation.isPending}
              className="flex items-center gap-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-700 text-white font-medium rounded-lg transition-colors"
            >
              {saveMcpMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              Save MCP Config
            </button>
          </div>
        </SectionCard>

        {/* Proxy Config */}
        <SectionCard title="MCP Proxy" icon={Network}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">
                Proxy Timeout (seconds)
              </label>
              <input
                type="number"
                value={proxyForm.timeout}
                onChange={(e) =>
                  setProxyForm((p) => ({ ...p, timeout: parseInt(e.target.value) || 86400 }))
                }
                className={inputClass + ' max-w-[160px]'}
              />
              <p className="text-xs text-gray-600 mt-1">
                Default 86400s (24h) for long-running MCP calls
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">
                Bearer Token (optional, for n8n proxy)
              </label>
              <div className="relative">
                <input
                  type={showBearerToken ? 'text' : 'password'}
                  value={proxyForm.bearer_token}
                  onChange={(e) => setProxyForm((p) => ({ ...p, bearer_token: e.target.value }))}
                  placeholder="Leave empty if not needed"
                  className={inputClass + ' pr-10'}
                />
                <button
                  type="button"
                  onClick={() => setShowBearerToken(!showBearerToken)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  {showBearerToken ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              onClick={() => saveProxyMutation.mutate(proxyForm)}
              disabled={saveProxyMutation.isPending}
              className="flex items-center gap-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-700 text-white font-medium rounded-lg transition-colors"
            >
              {saveProxyMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              Save Proxy Config
            </button>
          </div>
        </SectionCard>

        {/* Admin Password */}
        <SectionCard title="Admin Password" icon={Shield}>
          <div className="space-y-4">
            <p className="text-sm text-gray-500">
              Current: <code className="text-gray-400">{settings?.admin_password_masked}</code>
            </p>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">New Password</label>
              <input
                type="password"
                value={passwordForm.new_password}
                onChange={(e) =>
                  setPasswordForm((p) => ({ ...p, new_password: e.target.value }))
                }
                placeholder="Minimum 4 characters"
                className={inputClass + ' max-w-xs'}
              />
            </div>
            <button
              onClick={() => passwordMutation.mutate({ value: passwordForm.new_password })}
              disabled={passwordMutation.isPending || passwordForm.new_password.length < 4}
              className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 hover:bg-gray-700 disabled:bg-gray-800 disabled:text-gray-600 text-gray-300 font-medium rounded-lg transition-colors"
            >
              {passwordMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              Update Password
            </button>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}

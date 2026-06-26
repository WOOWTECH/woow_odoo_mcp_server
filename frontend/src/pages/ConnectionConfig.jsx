import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Link,
  Save,
  TestTube,
  Loader2,
  CheckCircle2,
  XCircle,
  Eye,
  EyeOff,
  KeyRound,
} from 'lucide-react';
import { apiGet, apiPut, apiPost } from '../api';

const inputClass =
  'w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 placeholder-gray-600 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition-colors';

export default function ConnectionConfig() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({});
  const [showSecret, setShowSecret] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet('/health'),
    staleTime: 60_000,
  });

  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => apiGet('/config'),
  });

  const appType = health?.app_type || 'odoo';
  const isN8n = appType === 'n8n';

  useEffect(() => {
    if (!config) return;
    if (isN8n) {
      setForm({
        n8n_api_url: config.n8n_api_url || '',
        n8n_api_key: '',
        mcp_session_timeout: config.mcp_session_timeout || 3600,
        mcp_max_sessions: config.mcp_max_sessions || 10,
      });
    } else {
      setForm({
        odoo_url: config.odoo_url || '',
        odoo_db: config.odoo_db || '',
        odoo_username: config.odoo_username || '',
        odoo_password: '',
      });
    }
  }, [config, isN8n]);

  const saveMutation = useMutation({
    mutationFn: (data) => apiPut('/config/connection', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] });
      queryClient.invalidateQueries({ queryKey: ['health'] });
    },
  });

  const testMutation = useMutation({
    mutationFn: () => apiPost('/config/test'),
    onSuccess: (result) => {
      setTestResult({ success: result.success, message: result.message || result.n8n_version || 'OK' });
    },
    onError: (err) => {
      setTestResult({ success: false, message: err.message });
    },
  });

  function handleChange(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
    setTestResult(null);
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-gray-500" size={24} />
      </div>
    );
  }

  const mainUrl = isN8n ? form.n8n_api_url : form.odoo_url;

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-100">Connection Configuration</h2>
        <p className="text-sm text-gray-500 mt-1">
          {isN8n ? 'Configure the connection to the n8n instance' : 'Configure the connection to the Odoo instance'}
        </p>
      </div>

      <form className="bg-gray-900 border border-gray-800 rounded-xl p-6 max-w-xl">
        <div className="space-y-4">
          {/* URL field — always present */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1.5">
              {isN8n ? 'n8n API URL' : 'Odoo URL'}
            </label>
            <div className="relative">
              <Link size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="url"
                value={mainUrl || ''}
                onChange={(e) => handleChange(isN8n ? 'n8n_api_url' : 'odoo_url', e.target.value)}
                placeholder={isN8n ? 'http://localhost:5678' : 'http://localhost:8069'}
                className={inputClass + ' pl-10'}
              />
            </div>
          </div>

          {isN8n ? (
            <>
              {/* n8n API Key */}
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1.5">
                  n8n API Key
                </label>
                <div className="relative">
                  <KeyRound size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                  <input
                    type={showSecret ? 'text' : 'password'}
                    value={form.n8n_api_key || ''}
                    onChange={(e) => handleChange('n8n_api_key', e.target.value)}
                    placeholder={config?.n8n_api_key_masked || 'Paste n8n API key'}
                    className={inputClass + ' pl-10 pr-10'}
                  />
                  <button
                    type="button"
                    onClick={() => setShowSecret(!showSecret)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                  >
                    {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <p className="text-xs text-gray-600 mt-1">
                  Generate in n8n: Settings &rarr; API &rarr; Create API Key
                </p>
              </div>

              {/* Session config */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1.5">
                    Session Timeout (s)
                  </label>
                  <input
                    type="number"
                    value={form.mcp_session_timeout || 3600}
                    onChange={(e) => handleChange('mcp_session_timeout', parseInt(e.target.value) || 3600)}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1.5">
                    Max Sessions
                  </label>
                  <input
                    type="number"
                    value={form.mcp_max_sessions || 10}
                    onChange={(e) => handleChange('mcp_max_sessions', parseInt(e.target.value) || 10)}
                    className={inputClass}
                  />
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Odoo fields */}
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1.5">Database</label>
                <input
                  type="text"
                  value={form.odoo_db || ''}
                  onChange={(e) => handleChange('odoo_db', e.target.value)}
                  placeholder="odoo"
                  className={inputClass}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1.5">Username</label>
                <input
                  type="text"
                  value={form.odoo_username || ''}
                  onChange={(e) => handleChange('odoo_username', e.target.value)}
                  placeholder="admin"
                  className={inputClass}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1.5">Password</label>
                <div className="relative">
                  <input
                    type={showSecret ? 'text' : 'password'}
                    value={form.odoo_password || ''}
                    onChange={(e) => handleChange('odoo_password', e.target.value)}
                    placeholder={config?.odoo_password_masked || 'Enter password'}
                    className={inputClass + ' pr-10'}
                  />
                  <button
                    type="button"
                    onClick={() => setShowSecret(!showSecret)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                  >
                    {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {testResult && (
          <div
            className={`mt-4 flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm ${
              testResult.success
                ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                : 'bg-red-500/10 border border-red-500/20 text-red-400'
            }`}
          >
            {testResult.success ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
            <span>{testResult.message}</span>
          </div>
        )}

        {saveMutation.isSuccess && (
          <div className="mt-4 flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <CheckCircle2 size={16} />
            <span>Configuration saved. MCP server will restart.</span>
          </div>
        )}

        {saveMutation.isError && (
          <div className="mt-4 flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm bg-red-500/10 border border-red-500/20 text-red-400">
            <XCircle size={16} />
            <span>{saveMutation.error.message}</span>
          </div>
        )}

        <div className="flex gap-3 mt-6">
          <button
            type="button"
            onClick={(e) => { e.preventDefault(); testMutation.mutate(); }}
            disabled={testMutation.isPending || !mainUrl}
            className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 hover:bg-gray-700 disabled:bg-gray-800 disabled:text-gray-600 text-gray-300 font-medium rounded-lg transition-colors"
          >
            {testMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <TestTube size={16} />}
            <span>Test Connection</span>
          </button>

          <button
            type="button"
            onClick={(e) => { e.preventDefault(); saveMutation.mutate(form); }}
            disabled={saveMutation.isPending || !mainUrl}
            className="flex items-center gap-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-medium rounded-lg transition-colors"
          >
            {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            <span>Save</span>
          </button>
        </div>
      </form>
    </div>
  );
}

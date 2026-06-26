import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  KeyRound,
  Copy,
  RefreshCw,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Eye,
  EyeOff,
  Clock,
} from 'lucide-react';
import { apiGet, apiPost } from '../api';

export default function TokenManager() {
  const queryClient = useQueryClient();
  const [showToken, setShowToken] = useState(false);
  const [newToken, setNewToken] = useState(null);
  const [copied, setCopied] = useState(false);
  const [confirmRotate, setConfirmRotate] = useState(false);

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiGet('/settings'),
  });

  const rotateMutation = useMutation({
    mutationFn: () => apiPost('/settings/mcp_auth_token/rotate'),
    onSuccess: (result) => {
      setNewToken(result.token);
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setConfirmRotate(false);
    },
  });

  const token = settings?.mcp_auth_token || '';
  const maskedToken = token
    ? token.substring(0, 8) + '...' + token.substring(token.length - 4)
    : 'No token configured';

  async function handleCopy() {
    const value = newToken || token;
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = value;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  const history = settings?.tools ? [] : []; // token_history is not in settings response by default
  // Read from a separate call if needed

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
        <h2 className="text-2xl font-bold text-gray-100">Token Manager</h2>
        <p className="text-sm text-gray-500 mt-1">Manage the MCP proxy authentication token</p>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 max-w-xl mb-6">
        <div className="flex items-center gap-2 mb-4">
          <KeyRound size={18} className="text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">
            Current Token
          </h3>
        </div>

        <div className="flex items-center gap-2 mb-4">
          <div className="flex-1 px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg font-mono text-sm text-gray-300 overflow-hidden">
            {showToken ? (newToken || token || 'No token') : maskedToken}
          </div>
          <button
            onClick={() => setShowToken(!showToken)}
            className="p-2.5 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg transition-colors"
            title={showToken ? 'Hide token' : 'Show token'}
          >
            {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
          <button
            onClick={handleCopy}
            disabled={!token && !newToken}
            className="p-2.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-400 hover:text-gray-200 border border-gray-700 rounded-lg transition-colors"
            title="Copy token"
          >
            {copied ? <CheckCircle2 size={16} className="text-brand-400" /> : <Copy size={16} />}
          </button>
        </div>

        {newToken && (
          <div className="mb-4 flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <CheckCircle2 size={16} />
            <span>New token generated. Copy and save it — it won't be shown again after refresh.</span>
          </div>
        )}

        <p className="text-xs text-gray-600 mb-4">
          MCP proxy URL: <code className="text-gray-400">/private_{'{token}'}/sse</code>
        </p>

        {!confirmRotate ? (
          <button
            onClick={() => setConfirmRotate(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-600/30 font-medium rounded-lg transition-colors"
          >
            <RefreshCw size={16} />
            <span>Rotate Token</span>
          </button>
        ) : (
          <div className="border border-amber-600/30 bg-amber-600/10 rounded-lg p-4">
            <div className="flex items-start gap-2 mb-3">
              <AlertTriangle size={18} className="text-amber-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium text-amber-300">Confirm Token Rotation</p>
                <p className="text-xs text-amber-400/70 mt-0.5">
                  This will generate a new token. All existing connections using the old token will stop working.
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => rotateMutation.mutate()}
                disabled={rotateMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:bg-gray-700 text-white font-medium rounded-lg text-sm transition-colors"
              >
                {rotateMutation.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <RefreshCw size={14} />
                )}
                <span>Confirm Rotate</span>
              </button>
              <button
                onClick={() => setConfirmRotate(false)}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-400 font-medium rounded-lg text-sm transition-colors"
              >
                Cancel
              </button>
            </div>

            {rotateMutation.isError && (
              <div className="mt-3 text-sm text-red-400">{rotateMutation.error.message}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

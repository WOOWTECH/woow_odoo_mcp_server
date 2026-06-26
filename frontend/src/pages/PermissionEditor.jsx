import React, { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Shield,
  Save,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  RotateCcw,
} from 'lucide-react';
import { apiGet, apiPut } from '../api';

export default function PermissionEditor() {
  const queryClient = useQueryClient();
  const [content, setContent] = useState('');
  const [parseError, setParseError] = useState(null);
  const [isDirty, setIsDirty] = useState(false);

  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => apiGet('/config'),
  });

  useEffect(() => {
    if (config?.permissions != null) {
      const formatted =
        typeof config.permissions === 'string'
          ? config.permissions
          : JSON.stringify(config.permissions, null, 2);
      setContent(formatted);
      setIsDirty(false);
      setParseError(null);
    }
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: (permissions) => apiPut('/config/permissions', { permissions }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] });
      setIsDirty(false);
    },
  });

  const validate = useCallback((text) => {
    if (!text.trim()) {
      return 'Content cannot be empty';
    }
    try {
      JSON.parse(text);
      return null;
    } catch (err) {
      return `JSON syntax error: ${err.message}`;
    }
  }, []);

  function handleChange(e) {
    const value = e.target.value;
    setContent(value);
    setIsDirty(true);
    const error = validate(value);
    setParseError(error);
  }

  function handleSave() {
    const error = validate(content);
    if (error) {
      setParseError(error);
      return;
    }
    try {
      const parsed = JSON.parse(content);
      saveMutation.mutate(parsed);
    } catch (err) {
      setParseError(err.message);
    }
  }

  function handleReset() {
    if (config?.permissions != null) {
      const formatted =
        typeof config.permissions === 'string'
          ? config.permissions
          : JSON.stringify(config.permissions, null, 2);
      setContent(formatted);
      setIsDirty(false);
      setParseError(null);
    }
  }

  function handleFormat() {
    try {
      const parsed = JSON.parse(content);
      setContent(JSON.stringify(parsed, null, 2));
      setParseError(null);
    } catch (err) {
      setParseError(`Cannot format: ${err.message}`);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-gray-500" size={24} />
      </div>
    );
  }

  const lineCount = content.split('\n').length;

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-100">Permission Editor</h2>
          <p className="text-sm text-gray-500 mt-1">
            Edit the MCP tool permission policy
            {isDirty && <span className="text-amber-400 ml-2">(unsaved changes)</span>}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleFormat}
            className="px-3 py-2 bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-gray-200 rounded-lg text-sm font-medium transition-colors"
          >
            Format JSON
          </button>

          <button
            onClick={handleReset}
            disabled={!isDirty}
            className="flex items-center gap-1.5 px-3 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:hover:bg-gray-800 text-gray-400 hover:text-gray-200 rounded-lg text-sm font-medium transition-colors"
          >
            <RotateCcw size={14} />
            <span>Reset</span>
          </button>

          <button
            onClick={handleSave}
            disabled={!!parseError || saveMutation.isPending || !isDirty}
            className="flex items-center gap-1.5 px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-medium rounded-lg text-sm transition-colors"
          >
            {saveMutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
            <span>Save</span>
          </button>
        </div>
      </div>

      {parseError && (
        <div className="flex items-center gap-2 px-3 py-2.5 mb-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
          <AlertCircle size={16} className="shrink-0" />
          <span className="font-mono text-xs">{parseError}</span>
        </div>
      )}

      {saveMutation.isSuccess && (
        <div className="flex items-center gap-2 px-3 py-2.5 mb-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-sm text-emerald-400">
          <CheckCircle2 size={16} />
          <span>Permissions saved. MCP server will restart with updated policy.</span>
        </div>
      )}

      {saveMutation.isError && (
        <div className="flex items-center gap-2 px-3 py-2.5 mb-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-400">
          <XCircle size={16} />
          <span>{saveMutation.error.message}</span>
        </div>
      )}

      <div className="flex-1 relative">
        <div className="absolute inset-0 flex bg-gray-950 border border-gray-800 rounded-xl overflow-hidden">
          <div className="py-3 px-2 bg-gray-900 text-right select-none border-r border-gray-800 overflow-y-auto shrink-0">
            {Array.from({ length: lineCount }, (_, i) => (
              <div key={i + 1} className="text-xs text-gray-600 leading-relaxed font-mono px-1">
                {i + 1}
              </div>
            ))}
          </div>
          <textarea
            value={content}
            onChange={handleChange}
            spellCheck={false}
            className="flex-1 p-3 bg-transparent text-gray-200 font-mono text-sm leading-relaxed resize-none focus:outline-none placeholder-gray-600 overflow-y-auto"
            placeholder='{"allowed_tools": ["*"], "denied_tools": []}'
          />
        </div>
      </div>

      <div className="flex items-center justify-between mt-3 text-xs text-gray-600">
        <div className="flex items-center gap-1">
          <Shield size={12} />
          <span>Permission policy (JSON)</span>
        </div>
        <span>
          {lineCount} lines &middot; {content.length} chars
        </span>
      </div>
    </div>
  );
}
